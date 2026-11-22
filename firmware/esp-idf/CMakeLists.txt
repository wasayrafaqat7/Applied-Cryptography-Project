# ESP-IDF project for the stale-key probe (also builds for the linux host target).
# Shared ratchet + SHA-256 code lives in ../common and is compiled into main/.
cmake_minimum_required(VERSION 3.16)
include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(stale_key_probe)
