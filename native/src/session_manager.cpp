#include "session_manager.hpp"
#include <fstream>

namespace rkedge {
SessionManager::SessionManager(std::size_t capacity, std::filesystem::path kv_directory)
    : capacity_(capacity), kv_directory_(std::move(kv_directory)) { std::filesystem::create_directories(kv_directory_); }

SessionState& SessionManager::acquire(const std::string& id) {
  std::lock_guard<std::mutex> lock(mutex_);
  auto [it, inserted] = sessions_.try_emplace(id, SessionState{id});
  it->second.last_access = std::chrono::steady_clock::now();
  if (it->second.status == "swapped") it->second.status = "resident";
  evict_if_needed();
  return it->second;
}

void SessionManager::evict_if_needed() {
  while (sessions_.size() > capacity_) {
    auto victim = sessions_.end();
    for (auto it = sessions_.begin(); it != sessions_.end(); ++it)
      if (victim == sessions_.end() || it->second.last_access < victim->second.last_access) victim = it;
    if (victim == sessions_.end()) break;
    std::ofstream(kv_directory_ / (victim->first + ".meta")) << victim->second.total_tokens << '\n';
    sessions_.erase(victim);
  }
}

bool SessionManager::clear(const std::string& id) {
  std::lock_guard<std::mutex> lock(mutex_);
  std::filesystem::remove(kv_directory_ / (id + ".meta"));
  return sessions_.erase(id) != 0;
}

bool SessionManager::swap_out(const std::string& id, const std::filesystem::path& supplied) {
  std::lock_guard<std::mutex> lock(mutex_);
  auto it = sessions_.find(id); if (it == sessions_.end()) return false;
  auto path = supplied.empty() ? kv_directory_ / (id + ".meta") : supplied;
  std::ofstream(path) << it->second.total_tokens << '\n';
  it->second.status = "swapped"; return true;
}

bool SessionManager::swap_in(const std::string& id, const std::filesystem::path& supplied) {
  std::lock_guard<std::mutex> lock(mutex_);
  auto path = supplied.empty() ? kv_directory_ / (id + ".meta") : supplied;
  std::ifstream input(path); if (!input) return false;
  auto& state = sessions_[id]; state.id = id; input >> state.total_tokens; state.status = "resident";
  state.last_access = std::chrono::steady_clock::now(); evict_if_needed(); return true;
}

std::optional<SessionState> SessionManager::inspect(const std::string& id) const {
  std::lock_guard<std::mutex> lock(mutex_);
  auto it = sessions_.find(id); return it == sessions_.end() ? std::nullopt : std::optional<SessionState>(it->second);
}
}

