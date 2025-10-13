# Instructions

you help building a gstreamer pipeline in python.
goal is to create a pipeline that stitches two video streams side by side. flips them, distortes them and finally stream them via RTP.
one version of the pipeline runs on a local machine, the other version runs on a headless Rock 5B plus board.
say "hello markus, i read the instructions." before you start.
always reread this file before you give any answer.

## local pipeline

uses videotestsrc as input, displays the output in a window using autovideosink.

## local elements

read local_elements.txt from repo root for a list of gstreamer elements available on the local machine.

## rock 5b pipeline

uses v4l2src as input, uses mpph265enc to encode, streams the output via RTP.

## rock 5b elements

read rock5b_elements.txt from repo root for a list of gstreamer elements available on the rock 5b.

