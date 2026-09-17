cmake_minimum_required(VERSION 3.16)
project(rk_inference_daemon LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
option(RKEDGE_WITH_RKNN3 "Build the RKNN3 Qwen2.5-Omni engine" OFF)
add_executable(rk_inference_daemon src/main.cpp src/session_manager.cpp)
target_include_directories(rk_inference_daemon PRIVATE include)
target_link_libraries(rk_inference_daemon PRIVATE pthread)
if(RKEDGE_WITH_RKNN3)
  set(MODEL_ZOO "/home/user/PycharmProjects/shize/RK3588/rknn3-model-zoo-main" CACHE PATH "RKNN3 model zoo")
  add_subdirectory(${MODEL_ZOO}/3rdparty ${CMAKE_BINARY_DIR}/model-zoo-3rdparty)
  add_subdirectory(${MODEL_ZOO}/utils ${CMAKE_BINARY_DIR}/model-zoo-utils)
  target_sources(rk_inference_daemon PRIVATE
    src/rknn_engine.cpp
    ${MODEL_ZOO}/examples/Qwen2_5_Omni/cpp/qwen2_5_omni.cc
    ${MODEL_ZOO}/examples/Qwen2_5_Omni/cpp/llm/rknn_qwen2_5_omni_llm.cc
    ${MODEL_ZOO}/examples/Qwen2_5_Omni/cpp/vision/rknn_qwen2_5_omni_vision.cc
    ${MODEL_ZOO}/examples/Qwen2_5_Omni/cpp/audio/rknn_qwen2_5_omni_audio.cc)
  target_compile_definitions(rk_inference_daemon PRIVATE RKEDGE_WITH_RKNN3=1)
  target_include_directories(rk_inference_daemon PRIVATE
    ${MODEL_ZOO}/examples/Qwen2_5_Omni/cpp
    ${MODEL_ZOO}/examples/Qwen2_5_Omni/cpp/llm
    ${MODEL_ZOO}/examples/Qwen2_5_Omni/cpp/vision
    ${MODEL_ZOO}/examples/Qwen2_5_Omni/cpp/audio
    ${LIBRKNNAPI_INCLUDES} ${LIBTOKENIZER_INCLUDES})
  target_link_libraries(rk_inference_daemon PRIVATE imageutils audioutils fileutils timeutils ${LIBRKNNAPI} ${LIBTOKENIZER} dl)
endif()
install(TARGETS rk_inference_daemon RUNTIME DESTINATION bin)
