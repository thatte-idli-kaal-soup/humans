#!/usr/bin/env python3

import argparse
from collections import namedtuple
import os
import subprocess
from textwrap import wrap

QnA = namedtuple("QnA", ["q", "a"], defaults=(None,))
FADE_IN = "fade=t=in:st=0:d=0.5"
FADE_OUT = "fade=t=out:st=2.5:d=0.5"
HERE = os.path.dirname(os.path.basename(__file__))
LOGO_FILE = os.path.join(HERE, "..", "logo_48x48.png")


def compute_drawtext_param(
    text, fontsize=18, fontcolor="FFFFFF", fontfile="Ubuntu-R.ttf", h_offset=0
):
    # Special character escapes are like violence: if they're not solving your
    # problem, you're not using enough. https://stackoverflow.com/a/10729560
    text = text.replace("'", "\\\\\\'")
    lines = wrap(text, width=32)
    fontconfig = f"fontfile={fontfile}:fontcolor={fontcolor}:fontsize={fontsize}"

    def format_line(text, idx):
        d = (idx + h_offset) * 7 / 2
        return f"drawtext={fontconfig}:text={text}:x='(w-tw)/2':y='(h+(th * {d}))/2'"

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
            text.a, fontsize=20, fontcolor="FF7F00", h_offset=h_offset
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


def draw_logo(input_file, output_file):
    command = [
        "ffmpeg",
        "-y",
        "-v",
        "0",
        "-i",
        input_file,
        "-i",
        LOGO_FILE,
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
    draw_logo("intro.mp4", "intro-logo.mp4")
    concat_videos("intro-logo.mp4", input_file, output_file)


def split_video(input_file, start, end, idx, crop):
    video_name = os.path.basename(input_file)
    start_seconds = str(to_seconds(start))
    end_seconds = str(to_seconds(end))
    output_file = f"part-{idx:02d}-{video_name}"
    command = [
        "ffmpeg",
        "-v",
        "0",
        "-y",
        "-i",
        input_file,
        "-ss",
        start_seconds,
        "-to",
        end_seconds,
        output_file,
    ]
    if crop:
        command.insert(-1, "-filter:v")
        command.insert(-1, f"crop={crop}")
    subprocess.check_call(command)
    return output_file


def to_seconds(timestamp):
    times = [float(x) for x in timestamp.split(".", 1)]
    return times[0] * 60 + times[1]


def main(video_path, timings, crop=None, n=None, with_intro=False):
    for idx, line in enumerate(timings, start=1):
        if n and idx != n:
            continue
        print(f"Creating part {idx} of {video_path}")
        columns = line.split(";", 1)
        (timing,) = columns[:1]
        start, end = timing.strip().split("-")
        output_file = split_video(video_path, start, end, idx, crop)
        if with_intro:
            if len(columns) > 1 and columns[1].strip():
                q_n_a = columns[1].strip().split(";")
                q_n_a = QnA(*q_n_a)
            else:
                q_n_a = QnA("hello world")
            prepend_text_video(output_file, output_file, q_n_a)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("input_dir", type=str)
    parser.add_argument("-n", type=int, help="Line number in the timings file")
    parser.add_argument("-I", "--with-intro", action="store_true", help="Add QnA intro")

    options = parser.parse_args()
    input_dir = os.path.abspath(options.input_dir)
    os.chdir(input_dir)
    video_name = "{}.mp4".format(os.path.basename(input_dir))

    with open("timings.txt") as f:
        timings = f.read().splitlines()

    if os.path.exists("crop.txt"):
        with open("crop.txt") as f:
            crop = f.read().strip()
    else:
        crop = ""

    main(video_name, timings, crop, options.n, options.with_intro)
