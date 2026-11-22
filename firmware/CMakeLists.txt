cmake_minimum_required(VERSION 3.16)

# Only build what main needs; keeps the build fast and works for the
# linux (host) target as well as esp32.
set(COMPONENTS main)

include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(stale_key_probe)
