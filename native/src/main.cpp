#include "session_manager.hpp"
#ifdef RKEDGE_WITH_RKNN3
#include "rknn_engine.hpp"
#endif
#include <atomic>
#include <csignal>
#include <cstring>
#include <filesystem>
#include <iostream>
#include <mutex>
#include <string>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <thread>
#include <unistd.h>
#include <vector>

namespace {
std::atomic<bool> running{true};
std::atomic<int> server_fd{-1};
std::mutex inference_mutex;
#ifdef RKEDGE_WITH_RKNN3
std::unique_ptr<rkedge::RknnEngine> engine;
#endif
std::string field(const std::string& json, const std::string& key) {
  const auto marker = "\"" + key + "\""; auto p = json.find(marker); if (p == std::string::npos) return {};
  p = json.find(':', p + marker.size()); if (p == std::string::npos) return {}; p = json.find('"', p); if (p == std::string::npos) return {};
  std::string out; for (++p; p < json.size(); ++p) { if (json[p] == '"') break; if (json[p] == '\\' && p + 1 < json.size()) ++p; out += json[p]; } return out;
}
std::string escaped(const std::string& text) { std::string out; for (char c : text) { if (c == '"' || c == '\\') out += '\\'; if (c == '\n') out += "\\n"; else out += c; } return out; }
bool valid_utf8(const std::string& text) {
  for (std::size_t i = 0; i < text.size();) {
    const auto c = static_cast<unsigned char>(text[i]);
    std::size_t continuation = c < 0x80 ? 0 : (c >= 0xc2 && c <= 0xdf ? 1 : (c >= 0xe0 && c <= 0xef ? 2 : (c >= 0xf0 && c <= 0xf4 ? 3 : 99)));
    if (continuation == 99 || i + continuation >= text.size()) return false;
    for (std::size_t j = 1; j <= continuation; ++j)
      if ((static_cast<unsigned char>(text[i + j]) & 0xc0) != 0x80) return false;
    i += continuation + 1;
  }
  return true;
}
std::vector<std::string> attachments(const std::string& json) { std::vector<std::string> out;auto p=json.find("\"attachments\"");if(p==std::string::npos)return out;p=json.find('[',p);auto end=json.find(']',p);while(p<end){p=json.find('"',p+1);if(p==std::string::npos||p>=end)break;auto e=json.find('"',p+1);if(e==std::string::npos||e>end)break;out.push_back(json.substr(p+1,e-p-1));p=e;}return out; }
void send_line(int fd, const std::string& line) { auto data = line + "\n"; ::send(fd, data.data(), data.size(), MSG_NOSIGNAL); }
void handle(int fd, rkedge::SessionManager& sessions) {
  std::string request; char buffer[4096]; ssize_t count;
  while ((count = ::recv(fd, buffer, sizeof(buffer), 0)) > 0) { request.append(buffer, count); if (request.find('\n') != std::string::npos) break; }
  auto action = field(request, "action"), conversation = field(request, "conversation_id"), request_id = field(request, "request_id");
  if (action == "clear") {
#ifdef RKEDGE_WITH_RKNN3
    if(engine){engine->clear(conversation,request.find("\"keep_system_prompt\": true")!=std::string::npos);send_line(fd,"{\"ok\":true}");}
    else
#endif
    send_line(fd, sessions.clear(conversation) ? "{\"ok\":true}" : "{\"ok\":true,\"already_clear\":true}");
  }
  else if (action == "swap_out") {
#ifdef RKEDGE_WITH_RKNN3
    if(engine)send_line(fd,engine->swap_out(conversation,field(request,"path"))?"{\"ok\":true}":"{\"ok\":false}");else
#endif
    send_line(fd, sessions.swap_out(conversation, field(request,"path")) ? "{\"ok\":true}" : "{\"ok\":false}");
  }
  else if (action == "swap_in") {
#ifdef RKEDGE_WITH_RKNN3
    if(engine)send_line(fd,engine->swap_in(conversation,field(request,"path"))?"{\"ok\":true}":"{\"ok\":false}");else
#endif
    send_line(fd, sessions.swap_in(conversation, field(request,"path")) ? "{\"ok\":true}" : "{\"ok\":false}");
  }
  else if (action == "stop") {
#ifdef RKEDGE_WITH_RKNN3
    if(engine){send_line(fd,engine->stop(conversation)?"{\"ok\":true}":"{\"ok\":false}");}
    else
#endif
    send_line(fd, "{\"ok\":true}");
  }
  else if (action == "generate") {
    std::lock_guard<std::mutex> serial(inference_mutex);
    auto& session = sessions.acquire(conversation); auto prompt = field(request, "prompt"); session.reused_tokens = session.total_tokens;
    send_line(fd, "{\"type\":\"phase\",\"phase\":\"prefill\",\"request_id\":\"" + escaped(request_id) + "\"}");
#ifdef RKEDGE_WITH_RKNN3
    if (engine) {
      try {
        auto media=attachments(request);std::string image_path,audio_path;for(const auto& path:media){auto dot=path.find_last_of('.');auto ext=dot==std::string::npos?std::string{}:path.substr(dot);if(ext==".wav"||ext==".mp3"||ext==".m4a"||ext==".webm")audio_path=path;else image_path=path;}
        // SentencePiece may return one UTF-8 code point split across callbacks. Buffer
        // incomplete byte sequences so every JSON line is independently valid UTF-8.
        std::string utf8_pending;
        auto metrics=engine->generate(conversation,prompt,image_path,audio_path,[&](const std::string& token){
          utf8_pending += token;
          if (valid_utf8(utf8_pending)) {
            send_line(fd,"{\"type\":\"token\",\"text\":\""+escaped(utf8_pending)+"\",\"request_id\":\""+escaped(request_id)+"\"}");
            utf8_pending.clear();
          }
        });
        if (!utf8_pending.empty()) send_line(fd,"{\"type\":\"token\",\"text\":\"\\uFFFD\",\"request_id\":\""+escaped(request_id)+"\"}");
        session.total_tokens=metrics.input_tokens+metrics.output_tokens;session.reused_tokens=metrics.reused_tokens;
        const double decode_s=(metrics.llm_ms-metrics.ttft_ms)/1000.0;const double decode_tps=decode_s>0?metrics.output_tokens/decode_s:0;
        send_line(fd,"{\"type\":\"done\",\"request_id\":\""+escaped(request_id)+"\",\"metrics\":{\"backend\":\"rknn3\",\"input_tokens\":"+std::to_string(metrics.input_tokens)+",\"output_tokens\":"+std::to_string(metrics.output_tokens)+",\"reused_tokens\":"+std::to_string(metrics.reused_tokens)+",\"vision_ms\":"+std::to_string(metrics.vision_ms)+",\"audio_ms\":"+std::to_string(metrics.audio_ms)+",\"ttft_ms\":"+std::to_string(metrics.ttft_ms)+",\"llm_ms\":"+std::to_string(metrics.llm_ms)+",\"total_ms\":"+std::to_string(metrics.total_ms)+",\"decode_tps\":"+std::to_string(decode_tps)+"}}");::close(fd);return;
      } catch(const std::exception& e){send_line(fd,"{\"type\":\"error\",\"error\":\""+escaped(e.what())+"\"}");::close(fd);return;}
    }
#endif
    const std::string response = "Native daemon 已收到请求。使用 RKNN3 构建选项部署后将由 RK1828 生成真实结果。";
    send_line(fd, "{\"type\":\"token\",\"text\":\"" + escaped(response) + "\",\"request_id\":\"" + escaped(request_id) + "\"}");
    session.total_tokens += prompt.size() / 2 + response.size() / 3;
    send_line(fd, "{\"type\":\"done\",\"request_id\":\"" + escaped(request_id) + "\",\"metrics\":{\"backend\":\"native-contract\",\"input_tokens\":" + std::to_string(prompt.size()/2) + ",\"output_tokens\":" + std::to_string(response.size()/3) + ",\"reused_tokens\":" + std::to_string(session.reused_tokens) + "}}");
  } else send_line(fd, "{\"type\":\"error\",\"error\":\"unknown_action\"}");
  ::close(fd);
}
}

int main(int argc, char** argv) {
  std::filesystem::path socket_path = argc > 1 ? argv[1] : "/run/rk-edge-ai/inference.sock";
  std::filesystem::path kv_path = argc > 2 ? argv[2] : "/userdata/rk-edge-ai/data/kv";
  std::filesystem::create_directories(socket_path.parent_path()); ::unlink(socket_path.c_str());
#ifdef RKEDGE_WITH_RKNN3
  if(const char* model_root=std::getenv("RKEDGE_MODEL_ROOT")) { try { engine=std::make_unique<rkedge::RknnEngine>(model_root); } catch(const std::exception& e) { std::cerr<<"RKNN3 init failed: "<<e.what()<<std::endl; return 3; } }
#endif
  int server = ::socket(AF_UNIX, SOCK_STREAM, 0); if (server < 0) return 1; server_fd=server;
  sockaddr_un address{}; address.sun_family = AF_UNIX; std::strncpy(address.sun_path, socket_path.c_str(), sizeof(address.sun_path)-1);
  if (::bind(server, reinterpret_cast<sockaddr*>(&address), sizeof(address)) < 0 || ::listen(server, 16) < 0) return 2;
  ::chmod(socket_path.c_str(), 0660); rkedge::SessionManager sessions(4, kv_path);
  auto stop=[](int){running=false;int fd=server_fd.exchange(-1);if(fd>=0){::shutdown(fd,SHUT_RDWR);::close(fd);}};
  std::signal(SIGINT, stop); std::signal(SIGTERM, stop);
  std::cout << "rk_inference_daemon listening on " << socket_path << std::endl;
  while (running) { int client = ::accept(server, nullptr, nullptr); if (client >= 0) std::thread(handle, client, std::ref(sessions)).detach(); }
  if(server_fd.exchange(-1)>=0)::close(server); ::unlink(socket_path.c_str());
}
