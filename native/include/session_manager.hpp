#pragma once
#include <chrono>
#include <filesystem>
#include <list>
#include <memory>
#include <mutex>
#include <optional>
#include <string>
#include <unordered_map>

namespace rkedge {
struct SessionState {
  std::string id;
  std::uint64_t total_tokens{};
  std::uint64_t reused_tokens{};
  std::string status{"resident"};
  std::chrono::steady_clock::time_point last_access{std::chrono::steady_clock::now()};
};

class SessionManager {
 public:
  explicit SessionManager(std::size_t capacity, std::filesystem::path kv_directory);
  SessionState& acquire(const std::string& id);
  bool clear(const std::string& id);
  bool swap_out(const std::string& id, const std::filesystem::path& path = {});
  bool swap_in(const std::string& id, const std::filesystem::path& path = {});
  std::optional<SessionState> inspect(const std::string& id) const;
 private:
  void evict_if_needed();
  std::size_t capacity_;
  std::filesystem::path kv_directory_;
  mutable std::mutex mutex_;
  std::unordered_map<std::string, SessionState> sessions_;
};
}

