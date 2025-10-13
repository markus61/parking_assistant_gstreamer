# Instructions

1. always reread this file before you give any answer. and confirm that by saying "hello markus, i read the instructions."
2. always reread this repository according to rules 2 and 3 from project file *rules.md* before you give any answer. and confirm that by saying "hello markus, i read the repository."
3. you help building a gstreamer pipeline in python.
4. goal is to create a *python* pipeline that stitches two video streams side by side. flips them, distortes them and finally stream them via RTP.
5. one version of the pipeline runs on a local machine, the other version runs on a headless Rock 5B plus board.

## local machine

## hardware

16 cores:
vendor_id       : GenuineIntel
cpu family      : 6
model           : 154
model name      : 12th Gen Intel(R) Core(TM) i7-1260P

16GB RAM

## os and drivers

ubuntu 24.04 LTS 64bit running Ubuntu Desktop


## local pipeline

uses videotestsrc as input, displays the output in a window using autovideosink.

## local elements

read https://raw.githubusercontent.com/markus61/parking_assistant_gstreamer/fakesrc/local_elements.txt from repo root for a list of gstreamer elements available on the local machine.

## rock 5b hardware

rock 5b plus board
8 cores: Rockchip RK3588

## os and drivers

debian bookworm 64bit running without desktop environment. with additional rockchip packages.
mali gpu with working opengles and panthor.
vpu with working hardware encoder  for H265
npu


## rock 5b pipeline

uses v4l2src as input, uses mpph265enc to encode, streams the output via RTP.

## rock 5b elements

read https://raw.githubusercontent.com/markus61/parking_assistant_gstreamer/fakesrc/rock5b_elements.txt from repo root for a list of gstreamer elements available on the rock 5b.

