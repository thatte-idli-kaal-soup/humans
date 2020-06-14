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
import tempfile
from textwrap import wrap

import click
from PIL import Image, ImageOps
import yaml

QnA = namedtuple("QnA", ["q", "a"], defaults=(None,))
HERE = os.path.dirname(os.path.basename(__file__))
LOGO_FILE = os.path.join(HERE, "..", "logo.png")
PART_FILENAME_FMT = "part-{idx:02d}-{video_name}"
FFMPEG_CMD = ["ffmpeg", "-y"]
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


def create_cover_video(cover_config, ext):
    w, h = cover_config["width"], cover_config["height"]
    background_file = f"black-{w}x{h}{ext}"
    input_file = cover_config["image"]
    output_file = f"cover{ext}"
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
    return output_file


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


def concat_videos(output_file, *inputs):
    with tempfile.NamedTemporaryFile("w", delete=False) as f:
        for input_file in inputs:
            p = os.path.abspath(input_file)
            f.write(f"file '{p}'\n")
    concat_command = FFMPEG_CMD + [
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        f.name,
        "-c",
        "copy",
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


def get_time(text):
    # Show questions based on reading speed of 2.5 words per second
    word_count = len(text.split())
    return min(max(4, round(word_count / 2.5)), 8)


def prepend_text_video(input_file, output_file, q_a):
    w, h = map(int, video_dimensions(input_file))
    text = f"{q_a.q} {q_a.a}"
    time = get_time(text)
    ext = os.path.splitext(input_file)[-1]
    background_file = f"black-{w}x{h}{ext}"
    create_black_background(input_file, background_file)
    font_height = int(h / 20)
    logo_size = int(h / 7.5)
    sha1 = hashlib.sha1(text.encode("utf-8")).hexdigest()
    text_file = f"intro-{sha1}-{w}x{h}{ext}"
    text_logo_file = f"intro-logo-{sha1}-{w}x{h}{ext}"
    draw_text(background_file, text_file, q_a, font_height, time)
    draw_logo(text_file, text_logo_file, logo_size, time)
    concat_videos(output_file, text_logo_file, input_file)


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


def create_video_segments(timings, idx):
    segments = []
    for sub_idx, params in enumerate(timings):
        video_name = params["video"]
        timing = params["time"]
        crop = params["crop"]
        start, end = timing.strip().split("-")
        segment_file = f"segment-{idx:02d}-{sub_idx:02d}-{video_name}"
        split_video(video_name, segment_file, start, end, crop)
        segments.append(segment_file)
    return segments


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
    for clip in config.get("clips", []):

        # Make timing into a dict with time
        timings = [t if isinstance(t, dict) else {"time": t} for t in clip["timings"]]
        clip["timings"] = timings
        clip_video = clip.pop("video", config["video"])
        clip_crop = clip.pop("crop", config.get("crop", ""))

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

    print(f"Creating low res video for {input_file}...")
    cmd = FFMPEG_CMD + ["-i", input_file, "-vf", f"scale={width}:{height}", output_file]
    subprocess.check_call(cmd)


def create_igtv_video(input_file, output_file):
    w, h = video_dimensions(input_file)
    new_h = int(h * 21 / 9)
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
    segments = create_video_segments(clip["timings"], idx)
    output_file = PART_FILENAME_FMT.format(
        idx=idx, video_name=clip["timings"][0]["video"]
    )
    concat_videos(output_file, *segments)
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
        intro_file = f"with-intro-{output_file}"
        prepend_text_video(output_file, intro_file, q_n_a)
        shutil.move(intro_file, output_file)

    path = os.path.abspath(output_file)
    print(f"Created {path}")


def get_clip_duration(clip):
    timings = [x["time"] for x in clip["timings"]]
    durations = [timing.strip().split("-") for timing in timings]
    durations = [(to_seconds(end) - to_seconds(start)) for start, end in durations]
    return sum(durations)


def create_background_music_file(config):
    timings = get_keyframe_timings(config)
    pairs = list(zip(timings[:-1], timings[1:]))
    ranges = [f"between(t,{start},{end})" for start, end in pairs]
    enabled = "+".join(ranges[::2])
    disabled = "+".join(ranges[1::2])
    trim = round(timings[-1], 2)
    bgm = config["bgm"]
    audio_file = os.path.abspath(bgm["audio"])
    ev = bgm["fg_volume"]
    dv = bgm["bg_volume"]
    background = "background.m4a"
    af = (
        f"[0:a]aloop=-1:2e+09,atrim=0:{trim},volume={ev}:enable='{enabled}',"
        f"volume={dv}:enable='{disabled}'"
    )
    cmd = FFMPEG_CMD + [
        "-i",
        audio_file,
        "-af",
        af,
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
        "[1:a]apad[bg],[0:a][bg]amerge=inputs=2[a]",
        "-map",
        "[a]",
        "-ac",
        "2",
        "-map",
        "0:v",
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


def add_background_music(input_video, config):
    background = create_background_music_file(config)
    first_video = config["clips"][0]["timings"][0]["video"]
    output_video = f"ALL-music-part-01-{first_video}"
    add_music_to_video(input_video, background, output_video)
    return output_video


def threshold_audio(input_file, output_file, config):
    audio_threshold = config["audio_threshold"]
    cmd = FFMPEG_CMD + [
        "-i",
        input_file,
        "-af",
        audio_threshold,
        "-c:v",
        "copy",
        output_file,
    ]
    subprocess.check_call(cmd)
    return output_file


@click.group()
@click.option("--loglevel", default="error")
@click.option("--profile/--no-profile", default=False)
@click.option("--use-original/--use-low-res", default=False)
@click.argument("config_file", type=click.File())
@click.pass_context
def cli(ctx, config_file, use_original, profile, loglevel):
    FFMPEG_CMD.extend(["-v", loglevel])
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
    config_data["debug"] = loglevel != "error"
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

    cover_config = config.get("cover")
    if cover_config:
        print("Creating cover video...")
        width, height = video_dimensions(first)
        ext = os.path.splitext(first)[-1]
        cover_config["width"] = width
        cover_config["height"] = height
        cover_video = create_cover_video(cover_config, ext)
        video_names.insert(0, cover_video)
        # Create padded cover image
        print("Creating IGTV cover image...")
        cover_image = cover_config["image"]
        igtv_cover = f"IGTV-{cover_image}"
        create_igtv_video(cover_image, igtv_cover)
    else:
        print(BOLDRED, "WARNING: No cover image has been specified!", ENDC, sep="")

    concat_videos(output_file, *video_names)
    path = os.path.abspath(output_file)
    print(f"Created {path}")
    # Threshold audio, if required
    if "audio_threshold" in config:
        threshold_file = f"thresholded-{output_file}"
        output_file = threshold_audio(output_file, threshold_file, config)
        threshold_path = os.path.abspath(threshold_file)
        print(f"Created {threshold_path}")
        output_file = threshold_file

    # Create musical version of video
    if "bgm" in config:
        output_file = add_background_music(output_file, config)
        output_path = os.path.abspath(output_file)
        print(f"Created {output_path}")

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
    segments = create_video_segments(config['trailer'], 0)
    video = config['video']
    output_file = f"trailer-{video}"
    concat_videos(output_file, *segments)
    path = os.path.abspath(output_file)
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
    print("No.\tQuestion & Answer\tDuration (s)\tQ time (s)")
    total_duration = 0
    for idx, clip in enumerate(clips, start=1):
        duration = get_clip_duration(clip)
        text = " + ".join(filter(None, [clip.get("question", ""), clip.get("answer")]))
        q_time = get_time(text.strip().strip("|").strip())
        print(f"{idx}\t{text}\t{duration:.1f}\t{q_time}")
        total_duration += duration
    print(f"Total duration: {total_duration}")


@cli.command()
@click.pass_context
def add_music(ctx):
    config = ctx.obj
    if "bgm" not in config:
        print("No audio file found in config!")
        return

    add_background_music(config)


if __name__ == "__main__":
    cli(obj={})
