#ifdef RKEDGE_WITH_RKNN3
#include "rknn_engine.hpp"
#include "qwen2_5_omni.h"
#include "audio_utils.h"
#include "image_utils.h"
#include "Tokenizer.h"
#include <chrono>
#include <cstring>
#include <fcntl.h>
#include <filesystem>
#include <functional>
#include <mutex>
#include <stdexcept>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unordered_map>
#include <unistd.h>
#include <vector>

const rknn3_sampling_params SAMPLE_PARAMS = {.top_k=1,.top_p=.9f,.temperature=1.f,.repeat_penalty=1.2f,.frequency_penalty=0.f,.presence_penalty=0.f};
const char* system_prompt="<|im_start|>system\nYou are a helpful assistant.<|im_end|>\n";
const char* prompt_prefix="<|im_start|>user\n";
const char* prompt_postfix="<|im_end|>\n<|im_start|>assistant\n";

namespace rkedge {
struct EmbedInfo { int fd{-1}; float16* data{}; std::size_t size{}; int dim{}, vocab{}; };
struct CallbackState { Tokenizer* tokenizer{}; std::function<void(const std::string&)> emit; std::chrono::steady_clock::time_point first_token{}; bool received{}; };
static int tokenizer_cb(void* u,const char* text,int32_t len,int32_t* tokens,int32_t max){return static_cast<Tokenizer*>(u)->Tokenize(text,len,tokens,max);}
static int embed_cb(void* u,int32_t* tokens,uint64_t n,void* output,uint64_t len){auto* e=static_cast<EmbedInfo*>(u);if(len!=n*e->dim*sizeof(float16))return -1;for(uint64_t i=0;i<n;++i)std::memcpy(static_cast<char*>(output)+i*e->dim*sizeof(float16),e->data+tokens[i]*e->dim,e->dim*sizeof(float16));return 0;}
static int result_cb(void* u,RKLLMResult* result,LLMCallState state){auto* c=static_cast<CallbackState*>(u);if(state==RKLLM_RUN_NORMAL){if(!c->received){c->first_token=std::chrono::steady_clock::now();c->received=true;}std::string piece=result->num_tokens==1?c->tokenizer->TokenToPiece(result->token_ids[0]):c->tokenizer->Decode(result->token_ids,result->num_tokens);c->emit(piece);}return 0;}

struct RknnEngine::Impl {
  rknn_app_context_t app{}; Tokenizer* tokenizer{}; EmbedInfo embed; rknn3_llm_param param{};
  std::unordered_map<std::string,rknn3_session*> sessions;
  std::unordered_map<std::string,std::chrono::steady_clock::time_point> last_access;
  std::mutex mutex; std::string root; std::filesystem::path kv_dir; std::size_t capacity{4};
  explicit Impl(std::string r):root(std::move(r)){
    kv_dir=std::getenv("RKEDGE_KV_DIR")?std::getenv("RKEDGE_KV_DIR"):"/userdata/rk-edge-ai/data/kv";
    std::filesystem::create_directories(kv_dir);
    auto path=[&](const char* n){return root+"/"+n;};
    auto tokenizer_path=path("Qwen2.5-Omni-3B-llm.tokenizer.gguf");
    tokenizer=new Tokenizer(TOKENIZER_BACKEND_LLAMA,tokenizer_path.c_str());
    VocabInfo vocab{};tokenizer->GetVocabInfo(&vocab);embed.fd=open(path("Qwen2.5-Omni-3B-llm.embed.bin").c_str(),O_RDONLY);if(embed.fd<0)throw std::runtime_error("embedding open failed");
    struct stat st{};if(fstat(embed.fd,&st))throw std::runtime_error("embedding stat failed");embed.size=st.st_size;embed.data=static_cast<float16*>(mmap(nullptr,embed.size,PROT_READ,MAP_PRIVATE,embed.fd,0));if(embed.data==MAP_FAILED)throw std::runtime_error("embedding mmap failed");embed.vocab=vocab.vocab_size;embed.dim=(embed.size/embed.vocab)/sizeof(float16);
    param.logits_name=(char*)"logits";param.max_context_len=1024;param.sampling_param=SAMPLE_PARAMS;param.vocab_info.vocab_size=vocab.vocab_size;param.vocab_info.n_special_eos_id=vocab.n_special_eos_id;param.vocab_info.n_special_bos_id=vocab.n_special_bos_id;std::memcpy(param.vocab_info.special_eos_id,vocab.special_eos_id,sizeof(vocab.special_eos_id));std::memcpy(param.vocab_info.special_bos_id,vocab.special_bos_id,sizeof(vocab.special_bos_id));param.vocab_info.linefeed_id=vocab.linefeed_id;
    CallbackState bootstrap{tokenizer,[](const std::string&){}};RKLLMCallback cb{};cb.result_callback=result_cb;cb.result_userdata=&bootstrap;cb.tokenizer_callback=tokenizer_cb;cb.tokenizer_userdata=tokenizer;cb.embed_callback=embed_cb;cb.embed_userdata=&embed;
    int ret=init_qwen2_5_omni_model(&app,path("Qwen2.5-Omni-3B-llm.rknn").c_str(),path("Qwen2.5-Omni-3B-llm.weight").c_str(),path("Qwen2.5-Omni-3B-vision.rknn").c_str(),path("Qwen2.5-Omni-3B-vision.weight").c_str(),path("Qwen2.5-Omni-3B-audio.rknn").c_str(),path("Qwen2.5-Omni-3B-audio.weight").c_str(),&param,1,cb,0xff,0xff,0xff);if(ret)throw std::runtime_error("RKNN3 model init failed: "+std::to_string(ret));
    sessions.emplace("__bootstrap__",app.llm.rknn_sess);
  }
  ~Impl(){for(auto& [id,s]:sessions)if(s&&s!=app.llm.rknn_sess)rknn3_session_destroy(s);sessions.clear();release_qwen2_5_omni_model(&app);if(embed.data&&embed.data!=MAP_FAILED)munmap(embed.data,embed.size);if(embed.fd>=0)close(embed.fd);delete tokenizer;}
  rknn3_session* session(const std::string& id){
    auto it=sessions.find(id);if(it!=sessions.end()){last_access[id]=std::chrono::steady_clock::now();return it->second;}
    if(sessions.size()>capacity){auto victim=last_access.end();for(auto pos=last_access.begin();pos!=last_access.end();++pos)if(pos->first!="__bootstrap__"&&(victim==last_access.end()||pos->second<victim->second))victim=pos;if(victim!=last_access.end()){auto sit=sessions.find(victim->first);if(sit!=sessions.end()){rknn3_session_save_kvcache(sit->second,(kv_dir/(victim->first+".kv")).c_str());rknn3_session_destroy(sit->second);sessions.erase(sit);}last_access.erase(victim);}}
    rknn3_session* s=rknn3_session_init(app.llm.rknn_ctx,&param,1);if(!s)throw std::runtime_error("session init failed");rknn3_session_set_chat_template(s,system_prompt,prompt_prefix,prompt_postfix);
    auto saved=kv_dir/(id+".kv");if(std::filesystem::exists(saved)&&rknn3_session_load_kvcache_from_path(s,saved.c_str())){rknn3_session_destroy(s);throw std::runtime_error("KV restore failed");}
    sessions[id]=s;last_access[id]=std::chrono::steady_clock::now();return s;
  }
};

RknnEngine::RknnEngine(const std::string& root):impl_(new Impl(root)){} RknnEngine::~RknnEngine()=default;
GenerateMetrics RknnEngine::generate(const std::string& id,const std::string& prompt,const std::string& image_attachment,const std::string& audio_attachment,const std::function<void(const std::string&)>& emit){
  std::lock_guard<std::mutex> lock(impl_->mutex);
  const auto total_start=std::chrono::steady_clock::now();
  auto* sess=impl_->session(id);CallbackState callback{impl_->tokenizer,emit};
  RKLLMCallback cb{};cb.result_callback=result_cb;cb.result_userdata=&callback;cb.tokenizer_callback=tokenizer_cb;cb.tokenizer_userdata=impl_->tokenizer;cb.embed_callback=embed_cb;cb.embed_userdata=&impl_->embed;
  if(rknn3_session_set_callback(sess,&cb))throw std::runtime_error("callback set failed");
  image_buffer_t image{};audio_buffer_t audio{};std::vector<float16> image_embed,audio_embed;
  bool use_image=prompt.find("<image>")!=std::string::npos,use_audio=prompt.find("<audio>")!=std::string::npos;
  double vision_ms=0,audio_ms=0;
  if(use_image){auto start=std::chrono::steady_clock::now();if(image_attachment.empty()||read_image(image_attachment.c_str(),&image))throw std::runtime_error("image read failed");size_t n=1;for(size_t i=0;i<impl_->app.vision.embeds_ndims;++i)n*=impl_->app.vision.embeds_shape[i];image_embed.resize(n);if(inference_qwen2_5_omni_vision(&impl_->app.vision,&image,image_embed.data()))throw std::runtime_error("vision inference failed");vision_ms=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-start).count();}
  if(use_audio){auto start=std::chrono::steady_clock::now();if(audio_attachment.empty()||read_audio(audio_attachment.c_str(),&audio))throw std::runtime_error("audio read failed");auto n=get_n_audio(&impl_->app.audio,audio.num_frames);audio_embed.resize(n*impl_->app.audio.embeds_dim1);if(inference_qwen2_5_omni_audio(&impl_->app.audio,&audio,audio_embed.data()))throw std::runtime_error("audio inference failed");audio_ms=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-start).count();}
  rknn3_llm_multimodal_tensor tensor{};tensor.name="input_embeds";tensor.prompt=prompt.c_str();tensor.image.image_embed=image_embed.data();tensor.image.n_image_tokens=impl_->app.vision.embeds_shape[0];tensor.image.n_image=use_image;tensor.image.image_width=impl_->app.vision.model_width;tensor.image.image_height=impl_->app.vision.model_height;tensor.image.image_start="<|vision_bos|>";tensor.image.image_end="<|vision_eos|>";tensor.image.image_content="<|IMAGE|>";tensor.audio.audio_embed=audio_embed.data();tensor.audio.n_audio_tokens=use_audio?get_n_audio(&impl_->app.audio,audio.num_frames):0;tensor.audio.n_audio=use_audio;tensor.audio.audio_start="<|audio_bos|>";tensor.audio.audio_end="<|audio_eos|>";tensor.audio.audio_content="<|AUDIO|>";
  rknn3_llm_input input{};input.input_type=RKNN3_LLM_INPUT_MULTIMODAL;input.multimodal_input=tensor;rknn3_llm_infer_param p{};p.keep_history=1;p.max_new_tokens=512;
  const auto llm_start=std::chrono::steady_clock::now();int ret=rknn3_session_run(sess,&input,1,&p);const auto end=std::chrono::steady_clock::now();
  if(image.virt_addr)free(image.virt_addr);if(audio.data)free(audio.data);if(ret)throw std::runtime_error("session run failed: "+std::to_string(ret));
  RKLLMRunState state{};rknn3_session_query_state(sess,&state);
  const double llm_ms=std::chrono::duration<double,std::milli>(end-llm_start).count();
  const double ttft=callback.received?std::chrono::duration<double,std::milli>(callback.first_token-llm_start).count():llm_ms;
  return {state.n_input_tokens,state.n_output_tokens,state.n_reuse_tokens,vision_ms,audio_ms,ttft,llm_ms,std::chrono::duration<double,std::milli>(end-total_start).count()};
}
bool RknnEngine::clear(const std::string& id,bool keep){std::lock_guard<std::mutex> l(impl_->mutex);std::filesystem::remove(impl_->kv_dir/(id+".kv"));auto it=impl_->sessions.find(id);return it==impl_->sessions.end()||rknn3_session_clear_kvcache(it->second,keep?RKNN3_KVCACHE_KEEP_SYSTEM_PROMPT:RKNN3_KVCACHE_CLEAR_ALL)==0;}
bool RknnEngine::stop(const std::string& id){auto it=impl_->sessions.find(id);return it!=impl_->sessions.end()&&rknn3_session_stop(it->second)==0;}
bool RknnEngine::swap_out(const std::string& id,const std::string& path){std::lock_guard<std::mutex> l(impl_->mutex);auto it=impl_->sessions.find(id);if(it==impl_->sessions.end())return true;auto target=path.empty()?impl_->kv_dir/(id+".kv"):std::filesystem::path(path);if(rknn3_session_save_kvcache(it->second,target.c_str()))return false;rknn3_session_destroy(it->second);impl_->sessions.erase(it);impl_->last_access.erase(id);return true;}
bool RknnEngine::swap_in(const std::string& id,const std::string& path){std::lock_guard<std::mutex> l(impl_->mutex);auto* s=impl_->session(id);auto default_path=impl_->kv_dir/(id+".kv");if(path.empty()||std::filesystem::path(path)==default_path)return true;return rknn3_session_load_kvcache_from_path(s,path.c_str())==0;}
}
#endif
