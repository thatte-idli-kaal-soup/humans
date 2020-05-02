#!/usr/bin/env python3

import argparse
from collections import namedtuple
import os
import subprocess
from textwrap import wrap

QnA = namedtuple("QnA", ["q", "a"])
FADE_IN = "fade=t=in:st=0:d=0.5"
FADE_OUT = "fade=t=out:st=2.5:d=0.5"


def compute_drawtext_param(
    text, fontsize=18, fontcolor="FFFFFF", fontfile="Ubuntu-R.ttf", h_offset=0
):
    lines = wrap(text, width=32)
    fontconfig = f"fontfile={fontfile}:fontcolor={fontcolor}:fontsize={fontsize}"

    def format_line(text, idx):
        d = (idx + h_offset) * 7 / 2
        return f"drawtext={fontconfig}:text='{text}':x='(w-tw)/2':y='(h+(th * {d}))/2'"

    return ",".join(format_line(line, i) for i, line in enumerate(lines))


def create_black_background(input_file, output_file, time=3):
    if os.path.isfile(output_file):
        return
    command = [
        "ffmpeg",
        "-v",
        "0",
        "-y",
        "-i",
        input_file,
        "-vf",
        f"trim=0:{time},geq=0:128:128",
        "-af",
        f"atrim=0:{time},volume=0",
        output_file,
    ]
    subprocess.check_call(command)


def draw_text(input_file, output_file, text):
    drawtext_param = compute_drawtext_param(text.q)
    if text.a:
        h_offset = drawtext_param.count("drawtext") + 1
        ans = compute_drawtext_param(
            text.a, fontsize=20, fontcolor="FFCC00", h_offset=h_offset
        )
        drawtext_param += f",{ans}"
    command = [
        "ffmpeg",
        "-v",
        "0",
        "-y",
        "-i",
        input_file,
        "-vf",
        f"{drawtext_param},{FADE_IN},{FADE_OUT}",
        output_file,
    ]
    subprocess.check_call(command)


def draw_logo(input_file, output_file, logo_file):
    command = [
        "ffmpeg",
        "-y",
        "-v",
        "0",
        "-i",
        input_file,
        "-i",
        logo_file,
        "-filter_complex",
        f"overlay=(main_w-overlay_w):10,{FADE_IN},{FADE_OUT}",
        output_file,
    ]
    subprocess.check_call(command)


def concat_videos(input_1, input_2, output_file):
    cmd = lambda infile, outfile: [
        "ffmpeg",
        "-y",
        "-v",
        "0",
        "-i",
        infile,
        "-c",
        "copy",
        "-bsf:v",
        "h264_mp4toannexb",
        "-f",
        "mpegts",
        outfile,
    ]
    inputs = (input_1, input_2)
    for i, intermediate_name in enumerate(("intermediate1.ts", "intermediate2.ts")):
        command = cmd(inputs[i], intermediate_name)
        subprocess.check_call(command)

    concat_command = [
        "ffmpeg",
        "-y",
        "-v",
        "0",
        "-i",
        "concat:intermediate1.ts|intermediate2.ts",
        "-c",
        "copy",
        "-bsf:a",
        "aac_adtstoasc",
        output_file,
    ]
    subprocess.check_call(concat_command)


def prepend_text_video(input_file, output_file, text):
    create_black_background(input_file, "black.mp4")
    draw_text("black.mp4", "intro.mp4", text)
    draw_logo("intro.mp4", "intro-logo.mp4", "logo_48x48.png")
    concat_videos("intro-logo.mp4", input_file, output_file)


def to_seconds(timestamp):
    times = [float(x) for x in timestamp.split(".", 1)]
    return times[0] * 60 + times[1]


def main(video_path, timings, n, crop=None):
    video_name = os.path.basename(video_path)
    for i, line in enumerate(timings, start=1):
        if n and i != n:
            continue
        start, end = line.split("-")
        start_seconds = to_seconds(start)
        end_seconds = to_seconds(end)
        duration = end_seconds - start_seconds
        command = [
            "ffmpeg",
            "-y",
            "-i",
            video_name,
            "-ss",
            str(start_seconds),
            "-t",
            str(duration),
            f"part-{i:02d}-{video_name}",
        ]
        if crop:
            command.insert(-1, "-filter:v")
            command.insert(-1, f"crop={crop}")
        subprocess.call(
            command, cwd=os.path.dirname(video_path),
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("video_file", type=str)
    parser.add_argument("timings", type=open)
    parser.add_argument("-n", type=int, help="Line number in the timings file")
    parser.add_argument("--crop", type=str, help="ffmpeg crop arguments")
    options = parser.parse_args()

    video_path = os.path.abspath(options.video_file)
    main(video_path, options.timings, options.n, options.crop)
