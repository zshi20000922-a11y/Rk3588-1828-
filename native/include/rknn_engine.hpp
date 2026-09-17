#pragma once
#ifdef RKEDGE_WITH_RKNN3
#include <functional>
#include <memory>
#include <string>

namespace rkedge {
struct GenerateMetrics {
  unsigned long long input_tokens{}, output_tokens{}, reused_tokens{};
  unsigned long long prompt_tokens{}, vision_tokens{}, embedding_tokens{}, embedding_calls{};
  int image_width{}, image_height{}, model_image_width{}, model_image_height{};
  double image_read_ms{}, image_preprocess_ms{}, vision_input_copy_ms{}, vision_input_sync_ms{};
  double vision_encoder_ms{}, vision_output_sync_ms{}, vision_embedding_copy_ms{}, vision_ms{};
  double multimodal_assembly_ms{}, text_embedding_ms{}, audio_ms{}, ttft_ms{}, llm_ms{}, total_ms{};
};
class RknnEngine {
 public:
  explicit RknnEngine(const std::string& model_root);
  ~RknnEngine();
  RknnEngine(const RknnEngine&) = delete;
  RknnEngine& operator=(const RknnEngine&) = delete;
  GenerateMetrics generate(const std::string& conversation_id, const std::string& prompt,
                           const std::string& image_attachment, const std::string& audio_attachment,
                           const std::function<void(const std::string&)>& token);
  bool clear(const std::string& conversation_id, bool keep_system_prompt);
  bool stop(const std::string& conversation_id);
  bool swap_out(const std::string& conversation_id, const std::string& path);
  bool swap_in(const std::string& conversation_id, const std::string& path);
 private:
  struct Impl; std::unique_ptr<Impl> impl_;
};
}
#endif
