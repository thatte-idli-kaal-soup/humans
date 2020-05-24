#!/usr/bin/env python3

import cProfile
from collections import namedtuple
import glob
import hashlib
import io
import multiprocessing
import os
import shutil
import subprocess
from textwrap import wrap

import click
from PIL import Image, ImageOps
import yaml

QnA = namedtuple("QnA", ["q", "a"], defaults=(None,))
HERE = os.path.dirname(os.path.basename(__file__))
LOGO_FILE = os.path.join(HERE, "..", "logo.png")
PART_FILENAME_FMT = "part-{idx:02d}-{video_name}"
FFMPEG_CMD = ["ffmpeg", "-v", "0", "-y"]
ENDC = "\033[0m"
BOLDRED = "\x1B[1;31m"
FADE_IN = "fade=t=in:st=0:d=0.5"


def get_fade_out(time):
    start = round(time - 0.5, 1)
    return f"fade=t=out:st={start}:d=0.5"


def compute_drawtext_param(
    text, width=32, fontsize=18, fontcolor="FFFFFF", fontfile="Ubuntu-R.ttf", h_offset=0
):
    # Special character escapes are like violence: if they're not solving your
    # problem, you're not using enough. https://stackoverflow.com/a/10729560
    text = text.replace("'", "\\\\\\'")
    text = text.replace(",", r"\,").replace(":", r"\\:")
    lines = [
        wrapped_line
        for each in text.splitlines()
        for wrapped_line in wrap(each, width=width)
    ]
    fontconfig = f"fontfile={fontfile}:fontcolor={fontcolor}:fontsize={fontsize}"

    def format_line(text, idx):
        d = (idx + h_offset) * 2.5
        # Text height depends on the height of the actual text - a sentence with
        # ... alone would have a very small height, compared to a "normal"
        # sentence. Use font-size instead.
        th = fontsize
        return f"drawtext={fontconfig}:text={text}:x='(w-tw)/2':y='(h+({th} * {d}))/2'"

    return ",".join(format_line(line, i) for i, line in enumerate(lines))


def create_black_background(input_file, output_file, time=10):
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


def create_cover_video(cover_config):
    w, h = cover_config["width"], cover_config["height"]
    background_file = f"black-{w}x{h}.mp4"
    input_file = cover_config["image"]
    output_file = "cover.mp4"
    time = cover_config["time"]
    FADE_OUT = get_fade_out(time)
    command = FFMPEG_CMD + [
        "-i",
        background_file,
        "-i",
        input_file,
        "-filter_complex",
        f"[0]trim=0:{time}[bg],[1]scale={w}:{h}[ovrl],[bg][ovrl]overlay=0:0,{FADE_IN},{FADE_OUT}",
        "-af",
        f"atrim=0:{time}",
        output_file,
    ]
    subprocess.check_call(command)
    return "cover.mp4"


def draw_text(input_file, output_file, text, font_height, time):
    drawtext_param = compute_drawtext_param(text.q, fontsize=font_height)
    FADE_OUT = get_fade_out(time)
    if text.a:
        h_offset = drawtext_param.count("drawtext") + 1
        ans_font_height = round(font_height * 1.1)
        ans = compute_drawtext_param(
            text.a, fontsize=ans_font_height, fontcolor="FF7F00", h_offset=h_offset,
        )
        drawtext_param += f",{ans}"
    command = FFMPEG_CMD + [
        "-i",
        input_file,
        "-vf",
        f"trim=0:{time},{drawtext_param},{FADE_IN},{FADE_OUT}",
        "-af",
        f"atrim=0:{time}",
        output_file,
    ]
    subprocess.check_call(command)


def resize_logo(logo, size):
    name = os.path.basename(logo)
    new_path = os.path.join(os.path.dirname(logo), f"{size}x{size}_{name}")
    if os.path.exists(new_path):
        return new_path

    with open(logo, "rb") as f:
        img = Image.open(io.BytesIO(f.read()))
    img = ImageOps.fit(img, (size, size), Image.ANTIALIAS)
    with open(new_path, "wb") as out:
        img.save(out, format="png")
    return new_path


def draw_logo(input_file, output_file, size=48, time=3):
    FADE_OUT = get_fade_out(time)
    logo_file = resize_logo(LOGO_FILE, size)
    command = FFMPEG_CMD + [
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
    intermediates = ["intermediate-{}.mkv".format(i) for i in inputs]
    for i, intermediate_name in enumerate(intermediates):
        command = generate_cmd(inputs[i], intermediate_name)
        subprocess.check_call(command)

    intermediates = "|".join(intermediates)
    concat_command = FFMPEG_CMD + [
        "-i",
        f"concat:{intermediates}",
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
    width, height = [int(x) for x in output.decode("utf8").strip().split(",")]
    return width, height


def get_audio_duration(input_file):
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "a:0",
        "-show_entries",
        "stream=duration",
        "-of",
        "csv=p=0",
        input_file,
    ]
    return float(subprocess.check_output(cmd).decode("utf8").strip())


def get_time(text):
    # Show questions based on reading speed of 2.5 words per second
    word_count = len(text.split())
    return min(max(4, round(word_count / 2.5)), 8)


def prepend_text_video(input_file, output_file, q_a):
    w, h = map(int, video_dimensions(input_file))
    text = f"{q_a.q} {q_a.a}"
    time = get_time(text)
    background_file = f"black-{w}x{h}.mp4"
    create_black_background(input_file, background_file)
    font_height = int(h / 20)
    logo_size = int(h / 7.5)
    sha1 = hashlib.sha1(text.encode("utf-8")).hexdigest()
    text_file = f"intro-{sha1}-{w}x{h}.mp4"
    text_logo_file = f"intro-logo-{sha1}-{w}x{h}.mp4"
    draw_text(background_file, text_file, q_a, font_height, time)
    draw_logo(text_file, text_logo_file, logo_size, time)
    concat_videos(text_logo_file, input_file, output_file)


def split_video(input_file, output_file, start, end, crop):
    start_seconds = to_seconds(start)
    end_seconds = to_seconds(end)
    duration = end_seconds - start_seconds
    command = FFMPEG_CMD + [
        # NOTE: Moving -ss before -i makes the cut super fast.
        # Note, -to is now the time in the output file (so duration of the cut)
        # See https://stackoverflow.com/a/49080616
        "-ss",
        str(start_seconds),
        "-i",
        input_file,
        "-to",
        str(duration),
        output_file,
    ]
    if crop:
        command.insert(-1, "-filter:v")
        command.insert(-1, f"crop={crop}")
    subprocess.check_call(command)


def split_and_concat_video(timings, idx):
    if len(timings) > 1:
        outputs = []
        for sub_idx, params in enumerate(timings):
            video_name = params["video"]
            timing = params["time"]
            crop = params["crop"]
            start, end = timing.strip().split("-")
            output_file = f"subpart-{idx:02d}-{sub_idx:02d}-{video_name}"
            split_video(video_name, output_file, start, end, crop)
            outputs.append((video_name, output_file))
        video_name, first = outputs[0]
        for sub_idx, (_, second) in enumerate(outputs[1:]):
            output_file = f"concat-{idx:02d}-{sub_idx:02d}-{video_name}"
            concat_videos(first, second, output_file)
            os.remove(first)
            os.remove(second)
            first = output_file
        output_file = PART_FILENAME_FMT.format(idx=idx, video_name=video_name)
        shutil.move(first, output_file)
    else:
        params = timings[0]
        video_name = params["video"]
        timing = params["time"]
        crop = params["crop"]
        start, end = timing.split("-")
        output_file = PART_FILENAME_FMT.format(idx=idx, video_name=video_name)
        split_video(video_name, output_file, start, end, crop)
    return output_file


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
    times = [float(x) for x in timestamp.split(":")]
    # Ignore hours, if present
    times = times[-2:]
    return times[0] * 60 + times[1]


def process_config(config, use_original):
    """Copy the video name to each clip item.

    If use_original is False, and alt_low_res is set, we use low resolution
    alternatives, instead of the originals.

    """
    alt_low_res = config.get("alt_low_res", {}) if not use_original else {}
    GLOBAL_KEYS = ("crop", "video")
    for clip in config.get("clips", []):

        # Make timing into a dict with time
        timings = [t if isinstance(t, dict) else {"time": t} for t in clip["timings"]]
        clip["timings"] = timings
        clip_video = clip.pop("video", config["video"])
        clip_crop = clip.pop("crop", config["crop"])

        for params in timings:
            video = params.pop("video", clip_video)
            params["video"] = alt_low_res.get(video, video)

            params.setdefault("crop", clip_crop)

    for each in config.get("trailer", []):
        video = each["video"]
        each["video"] = alt_low_res.get(video, video)
        each.setdefault("crop", config["crop"])


def create_low_res(input_file, output_file):
    width, height = video_dimensions(input_file)
    size = max(width, height)
    while size > 500:
        size /= 2
        width /= 2
        height /= 2

    cmd = FFMPEG_CMD + ["-i", input_file, "-vf", f"scale={width}:{height}", output_file]
    subprocess.check_call(cmd)


def create_igtv_video(input_file, output_file):
    w, h = video_dimensions(input_file)
    new_h = int(h * 16 / 9)
    pad_h = int((new_h - h) / 2)
    cmd = FFMPEG_CMD + [
        "-i",
        input_file,
        "-vf",
        f"pad={w}:{new_h}:0:{pad_h}",
        output_file,
    ]
    subprocess.check_call(cmd)


def process_clip(clip, with_intro, replace_image, idx):
    print(f"Creating part {idx}")
    output_file = split_and_concat_video(clip["timings"], idx)
    replacements = clip.get("replacements")
    if replacements is not None:
        output_file = do_all_replacements(output_file, replacements, replace_image)

    if with_intro:
        q = clip.get("question", "")
        a = clip.get("answer", "")
        if q:
            q_n_a = [q, a]
            q_n_a = QnA(*q_n_a)
        else:
            q_n_a = QnA("...")
        prepend_text_video(output_file, output_file, q_n_a)

    path = os.path.abspath(output_file)
    print(f"Created {path}")


def get_clip_duration(clip):
    timings = [x["time"] for x in clip["timings"]]
    durations = [timing.strip().split("-") for timing in timings]
    durations = [(to_seconds(end) - to_seconds(start)) for start, end in durations]
    return sum(durations)


def create_looped_audio(audio_file, trim):
    output = "looped.m4a"
    cmd = FFMPEG_CMD + [
        "-stream_loop",
        "-1",
        "-i",
        audio_file,
        "-t",
        f"{trim}",
        "-c:a",
        "aac",
        output,
    ]
    print("Creating looped audio...")
    subprocess.check_call(cmd)
    return output


def create_background_music(audio_file, trim, enabled, disabled):
    background = "background.m4a"
    cmd = FFMPEG_CMD + [
        "-i",
        audio_file,
        "-af",
        f"atrim=0:{trim},volume=0.4:enable='{enabled}',volume=0.1:enable='{disabled}'",
        "-c:a",
        "aac",
        background,
    ]
    print("Creating audio with volume enabled/disabled...")
    subprocess.check_call(cmd)
    return background


def add_music_to_video(input_video, input_audio, output_video):
    # https://superuser.com/a/712921
    cmd = FFMPEG_CMD + [
        "-i",
        input_video,
        "-i",
        input_audio,
        "-filter_complex",
        "[1:a]apad[bg],[0:a][bg]amerge",
        "-c:a",
        "aac",
        "-c:v",
        "copy",
        output_video,
    ]
    print("Adding background music to video...")
    subprocess.check_call(cmd)
    print(f"Created {output_video}")


def get_keyframe_timings(config):
    cover_time = config.get("cover", {}).get("time", 0)
    timings = []
    for clip in config["clips"]:
        duration = get_clip_duration(clip)
        q = clip.get("question", "")
        a = clip.get("answer", "")
        text = f"{q} {a}".strip()
        q_time = get_time(text)
        previous = timings[-1] if len(timings) > 0 else cover_time
        start = previous + q_time
        end = start + duration
        timings.append(round(start, 3))
        timings.append(round(end, 3))
    timings.insert(0, 0)
    return timings


@click.group()
@click.option("--profile/--no-profile", default=False)
@click.option("--use-original/--use-low-res", default=False)
@click.argument("config_file", type=click.File())
@click.pass_context
def cli(ctx, config_file, use_original, profile):
    config_data = yaml.load(config_file, Loader=yaml.FullLoader) or {}
    config_data["config_file"] = os.path.abspath(config_file.name)
    process_config(config_data, use_original)
    name = os.path.splitext(config_file.name)[0]
    config_data["name"] = name
    input_dir = os.path.abspath(name)
    os.chdir(input_dir)
    if profile:
        profile = cProfile.Profile()
        profile.enable()
        config_data["profile"] = profile
    ctx.obj.update(config_data)


@cli.command()
@click.option("--multi-process/--single-process", default=True)
@click.option("--replace-image", default=None)
@click.option("--with-intro/--no-intro", default=False)
@click.option("-n", default=0)
@click.pass_context
def process_clips(ctx, n, with_intro, replace_image, multi_process):
    config = ctx.obj
    clips = config["clips"]
    cpu_count = max(1, multiprocessing.cpu_count() - 1)

    if n == 0 and not with_intro:
        print(f"Intros will be generated even though --with-intro is off ...")
        with_intro = True

    if n > 0:
        process_clip(clips[n - 1], with_intro, replace_image, n)
    elif cpu_count == 1 or not multi_process:
        for idx, clip in enumerate(clips, start=1):
            process_clip(clip, with_intro, replace_image, idx)
    else:
        pool = multiprocessing.Pool(processes=cpu_count)
        n = len(clips)
        args = zip(clips, n * [with_intro], n * [replace_image], range(1, n + 1))
        pool.starmap(process_clip, args)

    if "profile" in config:
        profile = config["profile"]
        profile.dump_stats("profile.out")


@cli.command()
@click.pass_context
def combine_clips(ctx):
    config = ctx.obj
    video_names = [
        f"part-{idx:02d}-{clip['timings'][0]['video']}"
        for idx, clip in enumerate(config["clips"], start=1)
    ]
    missing_names = {name for name in video_names if not os.path.exists(name)}
    if missing_names:
        names = ", ".join(missing_names)
        raise RuntimeError(f"Create {names} before creating combined video")

    names = ", ".join(video_names)
    print(f"Combining {names} into a single video...")
    first = video_names[0]
    output_file = f"ALL-{first}"
    for second in video_names[1:]:
        concat_videos(first, second, output_file)
        first = output_file
    output_file = first  # This handles the case of video_names being a single item list
    path = os.path.abspath(output_file)
    print(f"Created {path}")
    width, height = video_dimensions(output_file)
    cover_config = config.get("cover")
    if cover_config:
        print("Prepending cover video...")
        cover_config["width"] = width
        cover_config["height"] = height
        cover_video = create_cover_video(cover_config)
        concat_videos(cover_video, output_file, output_file)
        # Create padded cover image
        cover_image = cover_config["image"]
        igtv_cover = f"IGTV-{cover_image}"
        create_igtv_video(cover_image, igtv_cover)
    else:
        print(BOLDRED, "WARNING: No cover image has been specified!", ENDC, sep="")

    print("Creating IGTV video...")
    igtv_file = os.path.abspath(f"IGTV-{output_file}")
    create_igtv_video(output_file, igtv_file)
    print(f"Created {igtv_file}")


@cli.command()
@click.pass_context
def make_trailer(ctx):
    config = ctx.obj
    if "trailer" not in config:
        click.echo("No configuration found for trailer!")
        return
    click.echo("Making trailer...")
    path = split_and_concat_video(config["trailer"], 0)
    click.echo(f"Created {path}")


@cli.command()
@click.option("--video-format", default="mp4")
@click.pass_context
def populate_config(ctx, video_format):
    config = ctx.obj
    videos = sorted(glob.glob(f"*.{video_format}"))
    name = config.pop("name")
    low_res_map = {}
    for idx, video in enumerate(videos, start=1):
        output_file = f"{name}-{idx:02d}.{video_format}"
        create_low_res(video, output_file)
        low_res_map[video] = output_file

    config_file = config.pop("config_file")
    config["clips"] = []
    config["video"] = videos[0]
    config["alt_low_res"] = low_res_map
    with open(config_file, "w") as f:
        yaml.dump(config, f)


@cli.command()
@click.pass_context
def print_index(ctx):
    config = ctx.obj
    clips = config["clips"]
    for idx, clip in enumerate(clips, start=1):
        duration = get_clip_duration(clip)
        text = " | ".join([clip.get("question", ""), clip.get("answer", "")])
        q_time = get_time(text.strip().strip("|").strip())
        print(f"{idx}\t{text}\t{duration:.1f}\t{q_time}")


@cli.command()
@click.pass_context
def add_music(ctx):
    config = ctx.obj
    if "audio" not in config:
        print("No audio file found in config!")
        return

    timings = get_keyframe_timings(config)
    pairs = list(zip(timings[:-1], timings[1:]))
    ranges = [f"between(t,{start},{end})" for start, end in pairs]
    enabled = "+".join(ranges[::2])
    disabled = "+".join(ranges[1::2])
    trim = round(timings[-1], 2)
    audio_file = os.path.abspath(config["audio"])
    duration = get_audio_duration(audio_file)

    if duration < trim:
        audio_file = create_looped_audio(audio_file, trim)

    background = create_background_music(audio_file, trim, enabled, disabled)
    first_video = config["clips"][0]["timings"][0]["video"]
    input_video = f"ALL-part-01-{first_video}"
    output_video = os.path.abspath(f"ALL-music-part-01-{first_video}")
    add_music_to_video(input_video, background, output_video)


if __name__ == "__main__":
    cli(obj={})
