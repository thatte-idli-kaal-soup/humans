#!/usr/bin/env python3

import argparse
from collections import namedtuple
import glob
import os
import shutil
import subprocess
from textwrap import wrap

import yaml

QnA = namedtuple("QnA", ["q", "a"], defaults=(None,))
FADE_IN = "fade=t=in:st=0:d=0.5"
FADE_OUT = "fade=t=out:st=2.5:d=0.5"
HERE = os.path.dirname(os.path.basename(__file__))
LOGO_FILE = os.path.join(HERE, "..", "logo_48x48.png")
PART_FILENAME_FMT = "part-{idx:02d}-{video_name}"
FFMPEG_CMD = ["ffmpeg", "-v", "0", "-y"]


def compute_drawtext_param(
    text, width=32, fontsize=18, fontcolor="FFFFFF", fontfile="Ubuntu-R.ttf", h_offset=0
):
    # Special character escapes are like violence: if they're not solving your
    # problem, you're not using enough. https://stackoverflow.com/a/10729560
    text = text.replace("'", "\\\\\\'")
    text = text.replace(",", r"\,").replace(":", r"\:")
    lines = wrap(text, width=width)
    fontconfig = f"fontfile={fontfile}:fontcolor={fontcolor}:fontsize={fontsize}"

    def format_line(text, idx):
        d = (idx + h_offset) * 2.5
        # Text height depends on the height of the actual text - a sentence with
        # ... alone would have a very small height, compared to a "normal"
        # sentence. Use font-size instead.
        th = fontsize
        return f"drawtext={fontconfig}:text={text}:x='(w-tw)/2':y='(h+({th} * {d}))/2'"

    return ",".join(format_line(line, i) for i, line in enumerate(lines))


def create_black_background(input_file, output_file, time=3):
    if os.path.isfile(output_file):
        return
    command = FFMPEG_CMD + [
        "-i",
        input_file,
        "-vf",
        f"trim=0:{time},geq=0:128:128",
        "-af",
        f"atrim=0:{time},volume=0",
        output_file,
    ]
    subprocess.check_call(command)


def draw_text(input_file, output_file, text, font_height, text_width):
    drawtext_param = compute_drawtext_param(text.q, text_width, font_height)
    if text.a:
        h_offset = drawtext_param.count("drawtext") + 1
        ans_font_height = round(font_height * 1.1)
        ans = compute_drawtext_param(
            text.a,
            width=text_width,
            fontsize=ans_font_height,
            fontcolor="FF7F00",
            h_offset=h_offset,
        )
        drawtext_param += f",{ans}"
    command = FFMPEG_CMD + [
        "-i",
        input_file,
        "-vf",
        f"{drawtext_param},{FADE_IN},{FADE_OUT}",
        output_file,
    ]
    subprocess.check_call(command)


def draw_logo(input_file, output_file):
    command = FFMPEG_CMD + [
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
    def generate_cmd(infile, outfile):
        cmd = FFMPEG_CMD + [
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
        return cmd

    inputs = (input_1, input_2)
    for i, intermediate_name in enumerate(("intermediate1.mkv", "intermediate2.mkv")):
        command = generate_cmd(inputs[i], intermediate_name)
        subprocess.check_call(command)

    concat_command = FFMPEG_CMD + [
        "-i",
        "concat:intermediate1.mkv|intermediate2.mkv",
        "-c",
        "copy",
        "-bsf:a",
        "aac_adtstoasc",
        output_file,
    ]
    subprocess.check_call(concat_command)


def video_dimensions(video):
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height",
        "-of",
        "csv=p=0",
        video,
    ]
    output = subprocess.check_output(cmd)
    width, height = [float(x) for x in output.decode("utf8").strip().split(",")]
    return width, height


def prepend_text_video(input_file, output_file, text):
    create_black_background(input_file, "black.mp4")
    width, height = video_dimensions(input_file)
    font_height = int(height / 20)
    text_width = int(width / 10)
    draw_text("black.mp4", "intro.mp4", text, font_height, text_width)
    draw_logo("intro.mp4", "intro-logo.mp4")
    concat_videos("intro-logo.mp4", input_file, output_file)


def split_video(input_file, output_file, start, end, crop):
    start_seconds = str(to_seconds(start))
    end_seconds = str(to_seconds(end))
    command = FFMPEG_CMD + [
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


def split_and_concat_video(video_name, timings, crop, idx):
    if len(timings) > 1:
        outputs = []
        for sub_idx, timing in enumerate(timings):
            start, end = timing.strip().split("-")
            output_file = f"subpart-{idx:02d}-{sub_idx:02d}-{video_name}"
            split_video(video_name, output_file, start, end, crop)
            outputs.append(output_file)
        first = outputs[0]
        for sub_idx, second in enumerate(outputs[1:]):
            output_file = f"concat-{idx:02d}-{sub_idx:02d}-{video_name}"
            concat_videos(first, second, output_file)
            os.remove(first)
            os.remove(second)
            first = output_file
        output_file = PART_FILENAME_FMT.format(idx=idx, video_name=video_name)
        shutil.move(first, output_file)
    else:
        start, end = timings[0].split("-")
        output_file = PART_FILENAME_FMT.format(idx=idx, video_name=video_name)
        split_video(video_name, output_file, start, end, crop)
    return output_file


def concat_all_parts(dir_name, config):
    num_parts = len(config["clips"])
    video_name = f"{dir_name}*.*"
    part_filename_pattern = PART_FILENAME_FMT.format(
        idx=0, video_name=video_name
    ).replace("-00-", "-*-")
    parts = sorted(glob.glob(part_filename_pattern))
    assert num_parts == len(parts), "Create all parts before running this"

    output_file = f"all-{dir_name}.mp4"
    first = parts[0]
    for second in parts[1:]:
        concat_videos(first, second, output_file)
        first = output_file
    print(f"Created {output_file}")


def do_all_replacements(input_file, replacements, replace_img):
    output_file = orig = input_file
    for replacement in replacements:
        start, end = [to_seconds(x) for x in replacement.strip().split("-")]
        output_file = f"{start}-{end}-{input_file}"
        input_file = replace_frames(input_file, output_file, start, end, replace_img)
    shutil.move(output_file, orig)
    return orig


def replace_frames(input_file, output_file, start, end, img):
    if not img:
        img = f"{output_file}.png"
        select = FFMPEG_CMD + [
            "-i",
            input_file,
            "-vf",
            f"select=gte(t\\,{start})",
            "-vframes",
            "1",
            img,
        ]
        subprocess.check_call(select)
    replace = FFMPEG_CMD + [
        "-i",
        input_file,
        "-i",
        img,
        "-filter_complex",
        f"[1][0]scale2ref[i][v];[v][i]overlay=x='if(gte(t,{start})*lte(t,{end}),0,NAN)'",
        "-c:a",
        "copy",
        output_file,
    ]
    subprocess.check_call(replace)
    return output_file


def to_seconds(timestamp):
    times = [float(x) for x in timestamp.split(":", 1)]
    return times[0] * 60 + times[1]


def process_config(config, use_original):
    """Copy the video name to each clip item.

    If use_original is False, and alt_low_res is set, we use low resolution
    alternatives, instead of the originals.

    """
    alt_low_res = config.get("alt_low_res", {}) if not use_original else {}
    GLOBAL_KEYS = ("crop", "video")
    for each in config["clips"]:
        for key in GLOBAL_KEYS:
            if key in config:
                value = each.setdefault(key, config[key])
                if key == "video" and alt_low_res:
                    each[key] = alt_low_res.get(value, value)


def main(config, n, with_intro, replace_img):
    clips = config["clips"]
    for idx, clip in enumerate(clips, start=1):
        if n and idx != n:
            continue
        print(f"Creating part {idx} of {clip['video']}")
        crop = clip.get("crop")
        output_file = split_and_concat_video(clip["video"], clip["timings"], crop, idx)
        replacements = clip.get("replacements")
        if replacements is not None:
            output_file = do_all_replacements(output_file, replacements, replace_img)

        if with_intro:
            q = clip.get("question", "")
            a = clip.get("answer", "")
            if q:
                q_n_a = [q, a]
                q_n_a = QnA(*q_n_a)
            else:
                q_n_a = QnA("...")
            prepend_text_video(output_file, output_file, q_n_a)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("config", type=open)
    parser.add_argument("-n", type=int, help="Line number in the timings file")
    parser.add_argument("-I", "--with-intro", action="store_true", help="Add QnA intro")
    parser.add_argument("-r", "--replace-frame", help="Image to use for replacement")
    parser.add_argument(
        "-u", "--use-original", action="store_true", help="Use originals (not low-res)"
    )
    parser.add_argument(
        "-a",
        "--combine-all",
        action="store_true",
        help="Create a single video from all the parts",
    )

    options = parser.parse_args()
    name = os.path.splitext(options.config.name)[0]
    config_file = os.path.abspath(options.config.name)
    input_dir = os.path.abspath(name)
    img = os.path.abspath(options.replace_frame) if options.replace_frame else ""
    os.chdir(input_dir)
    config_data = yaml.load(options.config, Loader=yaml.FullLoader)
    process_config(config_data, options.use_original)
    if options.combine_all:
        print("Combining all parts into a single video...")
        concat_all_parts(name, config_data)
    else:
        main(config_data, options.n, options.with_intro, img)
