#!/usr/bin/env python3

from collections import namedtuple
import os
import subprocess
from textwrap import wrap

QnA = namedtuple("QnA", ["q", "a"])


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
        f"{drawtext_param},fade=t=in:st=0:d=1,fade=t=out:st=3:d=1",
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
    create_black_background(input_file, "black.mp4", 4)
    draw_text("black.mp4", "intro.mp4", text)
    concat_videos("intro.mp4", input_file, output_file)


text = QnA(
    q="Which player inspires you to become a better player?", a="Ana from Airbenders"
)
prepend_text_video("nikki/part-05-nikki.mp4", "output.mp4", text)
