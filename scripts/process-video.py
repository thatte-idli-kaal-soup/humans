#!/usr/bin/env python3

import cProfile
from collections import namedtuple
import functools
import glob
import hashlib
import io
import math
import multiprocessing
import os
import subprocess
import tempfile
from textwrap import wrap
import time

import click
import helium as h
from PIL import Image, ImageOps
from selenium.webdriver import FirefoxProfile, FirefoxOptions
import yaml

QnA = namedtuple("QnA", ["q", "a"], defaults=(None,))
HERE = os.path.dirname(os.path.abspath(__file__))
LOGO_FILE = os.path.join(HERE, "..", "logo.png")
PART_FILENAME_FMT = "part-{idx:02d}-{video_name}"
FFMPEG_CMD = ["ffmpeg", "-y"]
ENDC = "\033[0m"
BOLDRED = "\x1B[1;31m"


def log_output_file(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        output = fn(*args, **kwargs)
        if output:
            print(f"Created {os.path.abspath(output)}")
        return output

    return wrapper


def get_fade_in(time):
    return f"fade=t=in:st={time}:d=0.5"


def get_fade_out(time):
    start = round(time - 0.5, 1)
    return f"fade=t=out:st={start}:d=0.5"


def compute_drawtext_param(
    text,
    width=32,
    fontsize=18,
    fontcolor="FFFFFF",
    fontfile="Ubuntu-R.ttf",
    h_offset=0,
    disable_wrap=False,
    animate=False,
):
    # Special character escapes are like violence: if they're not solving your
    # problem, you're not using enough. https://stackoverflow.com/a/10729560
    text = text.replace("'", "\u2019")
    text = text.replace(",", r"\,").replace(":", r"\:")
    if not disable_wrap:
        lines = [
            wrapped_line for each in text.splitlines() for wrapped_line in wrap(each, width=width)
        ]
    else:
        lines = text.splitlines()
    fontconfig = f"fontfile={fontfile}:fontcolor={fontcolor}:fontsize={fontsize}"

    def format_line(text, idx):
        d = (idx + h_offset) * 2.5
        # Text height depends on the height of the actual text - a sentence with
        # ... alone would have a very small height, compared to a "normal"
        # sentence. Use font-size instead.
        th = fontsize
        x = "(w-tw)/2"
        y = f"(h+({th} * {d}))/2"
        T = idx if animate else 0
        a = f"if(gte(t,{T}),min(1, t - {T}),0)"
        return f"drawtext={fontconfig}:text=\\'{text}\\':x='{x}':y='{y}':alpha='{a}'"

    return ",".join(format_line(line, i) for i, line in enumerate(lines))


def create_black_background(input_file, time=10):
    w, h = map(int, video_dimensions(input_file))
    name, ext = os.path.splitext(input_file)
    background_file = f"black-{name}-{w}x{h}{ext}"
    if os.path.isfile(background_file):
        return background_file
    command = (
        FFMPEG_CMD
        + ["-i", input_file]
        + ["-vf", f"trim=0:{time},geq=0:128:128", "-af", f"atrim=0:{time},volume=0"]
        + [background_file]
    )
    subprocess.check_call(command)
    return background_file


def create_cover_video(cover_config, ext):
    w, h = cover_config["width"], cover_config["height"]
    background_file = glob.glob(f"black-*-{w}x{h}{ext}")[0]
    input_file = cover_config["image"]
    output_file = f"cover-{w}x{h}{ext}"
    time = cover_config["time"]
    FADE_IN = get_fade_in(0)
    FADE_OUT = get_fade_out(time)
    command = (
        FFMPEG_CMD
        + ["-i", background_file, "-i", input_file]
        + [
            "-filter_complex",
            f"[0]trim=0:{time}[bg],[1]scale={w}:{h}[ovrl],[bg][ovrl]overlay=0:0,{FADE_IN},{FADE_OUT}",
        ]
        + ["-af", f"atrim=0:{time}", "-to", str(time), output_file]
    )
    subprocess.check_call(command)
    return output_file


def get_credits_text(config):
    entries = []
    n = max(map(len, map(str, config.keys())))
    m = max(map(len, map(str, config.values())))
    for key, value in config.items():
        if key == "time":
            continue
        title = key.replace("_", " ").upper()
        entry = f"{title:>{n}}\t{value:<{m}}".expandtabs(3)
        entries.append(entry)
    return "\n".join(entries)


def create_credits_video(input_file, credits_config):
    w, h = map(int, video_dimensions(input_file))
    time = credits_config.get("time", 2 + len(credits_config) * 2)
    text = get_credits_text(credits_config)
    ext = os.path.splitext(input_file)[-1]
    background_file = create_black_background(input_file)
    font_height = int(h / 28)
    logo_size = int(h / 7.5)
    sha1 = hashlib.sha1(text.encode("utf-8")).hexdigest()
    FADE_IN = get_fade_in(0)
    FADE_OUT = get_fade_out(time + 0.3)
    drawtext_param = compute_drawtext_param(
        text,
        fontsize=font_height,
        fontfile="UbuntuMono-B.ttf",
        disable_wrap=True,
        h_offset=-2,
        animate=True,
    )

    text_file = f"intro-{sha1}-{w}x{h}{ext}"
    command = (
        FFMPEG_CMD
        + ["-i", background_file]
        + ["-vf", f"trim=0:{time},{drawtext_param},{FADE_IN},{FADE_OUT}"]
        + ["-af", f"atrim=0:{time}"]
        + ["-to", str(time), text_file]
    )
    subprocess.check_call(command)

    text_logo_file = f"intro-logo-{sha1}-{w}x{h}{ext}"
    draw_logo(text_file, text_logo_file, logo_size, time)

    return text_logo_file


def draw_text(input_file, output_file, text, font_height, time):
    drawtext_param = compute_drawtext_param(text.q, fontsize=font_height)
    FADE_IN = get_fade_in(0)
    FADE_OUT = get_fade_out(time)
    if text.a:
        h_offset = drawtext_param.count("drawtext") + 1
        ans_font_height = round(font_height * 1.1)
        ans = compute_drawtext_param(
            text.a,
            fontsize=ans_font_height,
            fontcolor="FF7F00",
            h_offset=h_offset,
        )
        drawtext_param += f",{ans}"
    command = (
        FFMPEG_CMD
        + ["-i", input_file]
        + ["-vf", f"trim=0:{time},{drawtext_param},{FADE_IN},{FADE_OUT}"]
        + ["-af", f"atrim=0:{time}"]
        + ["-to", str(time), output_file]
    )
    subprocess.check_call(command)


def resize_logo(logo, size):
    name = os.path.basename(logo)
    new_path = os.path.join(os.path.dirname(logo), f"{size}x{size}_{name}")
    if os.path.exists(new_path):
        return new_path

    with open(logo, "rb") as f:
        img = Image.open(io.BytesIO(f.read()))
    img = ImageOps.fit(img, (size, size))
    with open(new_path, "wb") as out:
        img.save(out, format="png")
    return new_path


def create_square_image(image):
    img = Image.open(image)
    if img.height == img.width:
        return image

    size = max(img.height, img.width)
    new_img = Image.new("RGB", (size, size), color=None)
    padding = int(abs(img.height - img.width) / 2)
    position = (0, padding) if img.height < img.width else (padding, 0)
    new_img.paste(img, position)

    name, ext = os.path.splitext(image)
    output_file = f"{name}-padded{ext}"
    new_img.save(output_file, format="jpeg")
    return output_file


def draw_logo(
    input_file,
    output_file,
    size=48,
    time=3,
    logo_file=LOGO_FILE,
    location="(main_w-overlay_w):10",
):
    FADE_IN = get_fade_in(0)
    FADE_OUT = get_fade_out(time)
    logo_file = resize_logo(logo_file, size)
    command = (
        FFMPEG_CMD
        + ["-i", input_file, "-i", logo_file]
        + ["-filter_complex", f"overlay={location},{FADE_IN},{FADE_OUT}"]
        + [output_file]
    )
    subprocess.check_call(command)


@log_output_file
def concat_videos(output_file, inputs, use_container=False):
    # FIXME: Should we use this option everywhere?
    if use_container:
        n = len(inputs)
        f_i = "".join(f"[{i}:v:0][{i}:a:0]" for i in range(n))
        f_o = f"concat=n={n}:v=1:a=1[outv][outa]"
        f_args = [arg for f in inputs for arg in ("-i", f)]
        args = f_args + ["-filter_complex", f"{f_i}{f_o}", "-map", "[outv]", "-map", "[outa]"]
        if not output_file.endswith(".mkv"):
            output_file = f"{output_file}.mkv"
        concat_command = FFMPEG_CMD + args + [output_file]
        subprocess.check_call(concat_command)
    else:
        with tempfile.NamedTemporaryFile("w", delete=False) as f:
            for input_file in inputs:
                p = os.path.abspath(input_file)
                f.write(f"file '{p}'\n")
        concat_command = (
            FFMPEG_CMD + ["-f", "concat", "-safe", "0", "-i", f.name, "-c", "copy"] + [output_file]
        )
        subprocess.check_call(concat_command)
    return output_file


def video_dimensions(video):
    cmd = (
        ["ffprobe", "-v", "error"]
        + ["-select_streams", "v:0", "-show_entries", "stream=width,height"]
        + ["-of", "csv=p=0", video]
    )
    output = subprocess.check_output(cmd)
    width, height = [int(x) for x in output.decode("utf8").strip().split(",")]
    return width, height


def video_duration(video):
    cmd = (
        ["ffprobe", "-v", "error"]
        + ["-select_streams", "v:0", "-show_entries", "stream=duration"]
        + ["-of", "csv=p=0", video]
    )
    output = subprocess.check_output(cmd)
    return float(output.decode("utf8").strip())


def get_time(text):
    # Show questions based on reading speed of 2.5 words per second
    word_count = len(text.split())
    return min(max(4, round(word_count / 2.5)), 8)


def prepare_question_video(input_file, q_a):
    w, h = map(int, video_dimensions(input_file))
    text = f"{q_a.q} {q_a.a}"
    time = get_time(text)
    duration = video_duration(input_file)
    assert duration >= time, f"Too short segment for question slide: {input_file}, {text}"
    ext = os.path.splitext(input_file)[-1]
    background_file = create_black_background(input_file)
    font_height = int(h / 20)
    logo_size = int(h / 7.5)
    sha1 = hashlib.sha1(text.encode("utf-8")).hexdigest()
    text_file = f"intro-{sha1}-{w}x{h}{ext}"
    text_logo_file = f"intro-logo-{sha1}-{w}x{h}{ext}"
    draw_text(background_file, text_file, q_a, font_height, time)
    draw_logo(text_file, text_logo_file, logo_size, time)
    return text_logo_file


def split_video(input_file, output_file, start, end, crop, audio_filters=None):
    start_seconds = to_seconds(start)
    end_seconds = to_seconds(end)
    duration = end_seconds - start_seconds
    command = (
        FFMPEG_CMD
        # NOTE: Moving -ss before -i makes the cut super fast.
        # Note, -to is now the time in the output file (so duration of the cut)
        # See https://stackoverflow.com/a/49080616
        + ["-ss", str(start_seconds), "-i", input_file, "-to", str(duration)]
        + [output_file]
    )
    if crop:
        command.insert(-1, "-filter:v")
        command.insert(-1, f"crop={crop}")
    if audio_filters:
        command.insert(-1, "-af")
        command.insert(-1, audio_filters)
    subprocess.check_call(command)


def create_video_segments(timings, idx, replacements):
    segments = []
    for sub_idx, params in enumerate(timings):
        video_name = params["video"]
        timing = params["time"]
        crop = params["crop"]
        audio_filters = params.get("audio_filters")
        start, end = timing.strip().split("-")
        segment_file = f"segment-{idx:02d}-{sub_idx:02d}-{video_name}"
        split_video(video_name, segment_file, start, end, crop, audio_filters)
        replacements = params.get("replacements", [])
        if replacements:
            segment_file = do_all_replacements(segment_file, replacements)
        segments.append(segment_file)
    return segments


def do_all_replacements(input_file, replacements):
    for replacement in replacements:
        time = replacement["time"]
        replace_img = replacement.get("image", replacement.get("position", "start"))
        start, end = [to_seconds(x) for x in time.strip().split("-")]
        if replace_img in {"start", "end"}:
            position = start if replace_img == "start" else end
            replace_img = capture_screenshot(input_file, start, end, position)
        output_file = f"replaced-{start}-{end}-{input_file}"
        replace = (
            FFMPEG_CMD
            + ["-i", input_file, "-i", replace_img]
            + [
                "-filter_complex",
                f"[1][0]scale2ref[i][v];[v][i]overlay=x='if(gte(t,{start})*lte(t,{end}),0,NAN)'",
            ]
            + ["-c:a", "copy", output_file]
        )
        subprocess.check_call(replace)
        input_file = output_file
    return output_file


def create_overlay_video(input_file, photo, size):
    time = photo["time"]
    start, end = [to_seconds(x) for x in time.strip().split("-")]
    duration = end - start
    image = photo["photo"]
    print(f"Creating overlay video for {image}")
    ext = os.path.splitext(input_file)[-1]
    overlay_video = f"overlay-{os.path.basename(image)}{ext}"
    if photo.get("pad", False):
        image = create_square_image(image)
    image = resize_logo(image, size)
    FADE_IN = get_fade_in(0)
    FADE_OUT = get_fade_out(duration)
    command = (
        FFMPEG_CMD
        + ["-i", input_file, "-i", image]
        + ["-filter_complex", f"overlay=0,{FADE_IN},{FADE_OUT}"]
        + ["-t", str(duration), "-an", overlay_video]
    )
    subprocess.check_call(command)
    photo["video"] = overlay_video
    photo["start"] = start
    photo["end"] = end


@log_output_file
def overlay_photos(input_file, photos):
    # Create scaled images
    w, _ = video_dimensions(input_file)
    for photo in photos:
        create_overlay_video(input_file, photo, w)

    # Overlay videos
    n = len(photos)
    print(f"Overlaying {n} photos on video")
    output_file = f"photos-{input_file}"
    overlay_filter = [
        f"[{idx}]setpts=PTS-STARTPTS+{P['start']}/TB[v{idx}];"
        f"[out{idx-1}][v{idx}]overlay=enable='between(t,{P['start']},{P['end']})'[out{idx}]"
        for idx, P in enumerate(photos, start=1)
    ]
    filter_complex = ";".join(overlay_filter).replace("out0", "0").replace(f"[out{n}]", "")
    command = (
        FFMPEG_CMD
        + ["-i", input_file]
        + [arg for photo in photos for arg in ["-i", photo["video"]]]
        + ["-filter_complex", filter_complex, output_file]
    )
    subprocess.check_call(command)
    return output_file


def capture_screenshot(input_file, start, end, position):
    img = f"{input_file}-{position}.png"
    select = (
        FFMPEG_CMD
        + ["-i", input_file]
        + ["-vf", f"select=gte(t\\,{position})", "-vframes", "1", img]
    )
    subprocess.check_call(select)
    return img


def to_seconds(timestamp):
    times = [float(x) for x in timestamp.split(":")]
    seconds = [math.pow(60, idx) * t for idx, t in enumerate(times[::-1])]
    return sum(seconds)


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
        video = each.get("video", config["video"])
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


@log_output_file
def create_igtv_video(input_file, output_file):
    w, h = video_dimensions(input_file)
    new_h = int(h * 21 / 9)
    pad_h = int((new_h - h) / 2)
    cmd = FFMPEG_CMD + ["-i", input_file] + ["-vf", f"pad={w}:{new_h}:0:{pad_h}", output_file]
    subprocess.check_call(cmd)


@log_output_file
def process_clip(clip, with_intro, idx):
    print(f"Creating part {idx}")
    replacements = clip.get("replacements")
    segments = create_video_segments(clip["timings"], idx, replacements)
    output_file = PART_FILENAME_FMT.format(idx=idx, video_name=clip["timings"][0]["video"])

    if with_intro:
        q = clip.get("question", "")
        a = clip.get("answer", "")
        if q:
            q_n_a = [q, a]
            q_n_a = QnA(*q_n_a)
        else:
            q_n_a = QnA("...")
        segment_timings = zip([get_segment_duration(s) for s in clip["timings"]], segments)
        longest_segment = sorted(segment_timings, reverse=True)[0][-1]
        intro_file = prepare_question_video(longest_segment, q_n_a)
        segments.insert(0, intro_file)

    concat_videos(output_file, segments)
    return output_file


def get_segment_duration(segment):
    timing = segment["time"]
    start, end = timing.strip().split("-")
    return to_seconds(end) - to_seconds(start)


def get_clip_duration(clip):
    durations = [get_segment_duration(segment) for segment in clip["timings"]]
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

    # Fade in the music at the start
    st = timings[0]
    d = timings[1] - st
    afade = f"afade=t=in:st={st}:d={d}:curve=squ"

    af = (
        f"[0:a]atrim=0:{trim},{afade},volume={ev}:enable='{enabled}',"
        f"volume={dv}:enable='{disabled}'"
    )

    # Fade out the music at the end
    st = timings[-2]
    d = timings[-1] - st
    afade = f"afade=t=out:st={st}:d={d}:curve=qsin"
    af += f",{afade}"

    cmd = (
        FFMPEG_CMD
        + ["-stream_loop", "100", "-i", audio_file]
        + ["-af", af, "-c:a", "aac", background]
    )
    print("Creating audio with volume enabled/disabled...")
    subprocess.check_call(cmd)
    return background


@log_output_file
def add_music_to_video(input_video, input_audio, output_video):
    cmd = (
        FFMPEG_CMD
        + ["-i", input_video, "-i", input_audio, "-async", "1"]
        + ["-filter_complex", "[0][1]amix=inputs=2[a]"]
        + ["-map", "[a]", "-map", "0:v", "-c:v", "copy", "-c:a", "aac", output_video]
    )
    print("Adding background music to video...")
    subprocess.check_call(cmd)
    return output_video


def get_keyframe_timings(config):
    cover_time = config.get("cover", {}).get("time", 0)
    credits_time = config.get("credits", {}).get("time", 0)
    timings = []
    for idx, clip in enumerate(config["clips"], start=1):
        video = f"part-{idx:02d}-{clip['timings'][0]['video']}"
        duration = video_duration(video)  # includes intro slide time
        q = clip.get("question", "")
        a = clip.get("answer", "")
        text = f"{q} {a}".strip()
        q_time = get_time(text)
        previous = timings[-1] if len(timings) > 0 else cover_time
        start = previous + q_time
        end = previous + duration
        timings.append(round(start, 3))
        timings.append(round(end, 3))
    timings.insert(0, 0)
    timings.append(round(end + credits_time, 3))
    if config["debug"]:
        print(timings)
    return timings


def get_music_filename(config):
    first_video = config["clips"][0]["timings"][0]["video"]
    return f"ALL-music-{first_video}"


@log_output_file
def add_background_music(input_video, config):
    if "bgm" not in config:
        return input_video

    background = create_background_music_file(config)
    output_video = get_music_filename(config)
    add_music_to_video(input_video, background, output_video)
    return output_video


@log_output_file
def threshold_audio(input_file, output_file, config):
    audio_threshold = config["audio_threshold"]
    cmd = FFMPEG_CMD + ["-i", input_file] + ["-af", audio_threshold, "-c:v", "copy", output_file]
    subprocess.check_call(cmd)
    return output_file


def instagram_caption(config):
    description = config.get("description", "")
    keywords = " ".join(config.get("keywords", [])).strip()
    caption = f"{description}\n\n{keywords}".strip()
    return caption


def youtube_description(config):
    description = config.get("description", "")
    chapters = youtube_chapters_text(config)
    text = f"{description}\n\n{chapters}".strip()
    return text


def youtube_chapters_text(config):
    start_timings = get_keyframe_timings(config)[::2][:-1]
    chapters = []
    for idx, seconds in enumerate(start_timings):
        question = config["clips"][idx]["question"]
        start = time.strftime("%M:%S", time.gmtime(seconds))
        chapters.append(f"{start} - {question}")
    return "\n".join(chapters)


def upload_to_youtube(upload_file, cover_image, title, description):
    options = FirefoxOptions()
    profile_dir = os.environ["FF_PROFILE"]
    options.profile = FirefoxProfile(profile_dir)
    driver = h.start_firefox("studio.youtube.com", options=options)
    h.click("Upload videos")
    file_input = "//input[@name='Filedata']"
    element = driver.find_element_by_xpath(file_input)
    element.send_keys(upload_file)
    h.write(title, into=h.TextField("Title (required)"))
    h.write(description, into=h.TextField("Description"))
    element = driver.find_element_by_id("file-loader")
    element.send_keys(cover_image)
    # FIXME: Figure out this... or just use selenium
    # h.click(h.Text("Playlists"))
    # h.click(h.CheckBox("Humans of TIKS"))
    # h.click(h.RadioButton("No, it's not made for kids"))


def upload_to_instagram(upload_file, cover_image, title, description):
    options = FirefoxOptions()
    profile_dir = os.environ["FF_PROFILE"]
    options.profile = FirefoxProfile(profile_dir)
    driver = h.start_firefox("instagram.com/tiks_ultimate/channel", options=options)
    h.click(h.Button("Upload"))
    h.write(title, into="Title")
    h.write(description, into="Description")

    file_input = "//input[@type='file']"
    element = driver.find_element_by_xpath(file_input)
    element.send_keys(upload_file)

    time.sleep(3)
    element = driver.find_elements_by_xpath(file_input)[-1]
    element.send_keys(cover_image)


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
    name = os.path.basename(os.path.splitext(config_file.name)[0])
    config_data["name"] = name
    input_dir = os.path.join(os.path.abspath("media"), name)
    os.chdir(input_dir)
    if profile:
        profile = cProfile.Profile()
        profile.enable()
        config_data["profile"] = profile
    config_data["debug"] = loglevel != "error"
    ctx.obj.update(config_data)


@cli.command()
@click.option("--multi-process/--single-process", default=True)
@click.option("--with-intro/--no-intro", default=False)
@click.option("-n", default=0)
@click.pass_context
def process_clips(ctx, n, with_intro, multi_process):
    config = ctx.obj
    clips = config["clips"]
    cpu_count = max(1, multiprocessing.cpu_count() - 1)

    if n == 0 and not with_intro:
        print("Intros will be generated even though --with-intro is off ...")
        with_intro = True
        # Generate black background before processing the clips
        timing = clips[0]["timings"][0]
        input_file = timing["video"]
        output_file = f"black-input-{input_file}"
        split_video(input_file, output_file, "0:0", "0:20", timing["crop"])
        create_black_background(output_file)

    if n > 0:
        process_clip(clips[n - 1], with_intro, n)
    elif cpu_count == 1 or not multi_process:
        for idx, clip in enumerate(clips, start=1):
            process_clip(clip, with_intro, idx)
    else:
        pool = multiprocessing.Pool(processes=cpu_count)
        n = len(clips) + 1
        args = zip(clips, n * [with_intro], range(1, n + 1))
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

    credits = config.get("credits")
    if credits:
        print("Creating credits video...")
        credits_video = create_credits_video(first, credits)
        video_names.append(credits_video)

    output_file = concat_videos(output_file, video_names, use_container=True)

    # Add image slideshow
    photos = config.get("photos")
    if photos:
        output_file = overlay_photos(output_file, photos)

    # Threshold audio, if required
    if "audio_threshold" in config:
        threshold_file = f"thresholded-{output_file}"
        output_file = threshold_audio(output_file, threshold_file, config)

    # Create musical version of video
    output_file = add_background_music(output_file, config)

    print("Creating IGTV video...")
    igtv_file = os.path.abspath(f"IGTV-{output_file}")
    create_igtv_video(output_file, igtv_file)


@cli.command()
@click.pass_context
def make_trailer(ctx):
    config = ctx.obj
    if "trailer" not in config:
        click.echo("No configuration found for trailer!")
        return
    click.echo("Making trailer...")
    segments = create_video_segments(config["trailer"], 0, [])
    video = config["video"]
    output_file = f"trailer-{video}"
    concat_videos(output_file, segments)
    if "audio_threshold" in config:
        threshold_file = f"thresholded-{output_file}"
        threshold_audio(output_file, threshold_file, config)


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
        total_duration += duration + q_time
    print(f"Total duration: {total_duration}")


@cli.command()
@click.pass_context
@click.argument("video", type=click.File())
def add_music(ctx, video):
    add_background_music(video.name, ctx.obj)


@cli.command()
@click.pass_context
@click.argument("video", type=click.File())
def add_photos(ctx, video):
    photos = ctx.obj.get("photos")
    if photos:
        output_file = overlay_photos(video.name, photos)


@cli.command()
@click.pass_context
def clean_workdir(ctx):
    paths = [
        path
        for prefix in {
            "part-",
            "replaced-",
            "intro-",
            "segment-",
            "black-",
            "thresholded-",
            "background.m4a",
        }
        for path in glob.glob(f"{prefix}*")
    ]
    for path in paths:
        os.remove(path)


@cli.command()
@click.pass_context
@click.argument("video", type=click.File())
def project_add_video(ctx, video):
    config = ctx.obj
    ext = os.path.splitext(video.name)[-1]
    n = len(config["alt_low_res"]) + 1
    name = config["name"]
    output_file = f"{name}-{n:02d}{ext}"
    create_low_res(video.name, output_file)


@cli.command()
@click.pass_context
def create_flac_audio(ctx):
    config = ctx.obj
    for key in config["alt_low_res"]:
        command = FFMPEG_CMD + ["-i", key, "-ac", "1", "-vn", f"{key}.flac"]
        print(f"Creating Flac audio for {key}...")
        subprocess.check_call(command)


@cli.command()
@click.pass_context
def gs_upload_flac_audio(ctx):
    command = [
        "gsutil",
        "-m",
        "cp",
        "*.flac",
        "gs://transcription-audio-humans-of-tiks/",
    ]
    subprocess.check_call(command)


@cli.command()
@click.pass_context
def youtube_chapters(ctx):
    config = ctx.obj
    chapters = youtube_chapters_text(config)
    print(chapters)


@cli.command()
@click.pass_context
def youtube_upload(ctx):
    config = ctx.obj
    assert ctx.parent.params["use_original"], "Please call the command with use original"
    # FIXME: We assume we are only going to upload videos with music, which is
    # good enough for now!
    upload_file = os.path.abspath(get_music_filename(config))
    name = config["name"].capitalize()
    title = f"{name} - Humans of TIKS"
    description = youtube_description(config)
    cover_image = os.path.abspath(config["cover"]["image"])
    # FIXME: Check that file size is less than 2MB
    upload_to_youtube(upload_file, cover_image, title, description)


@cli.command()
@click.pass_context
def instagram_upload(ctx):
    config = ctx.obj
    assert ctx.parent.params["use_original"], "Please call the command with use original"
    # FIXME: We assume we are only going to upload videos with music, which is
    # good enough for now!
    music_file = get_music_filename(config)
    upload_file = os.path.abspath(f"IGTV-{music_file}")
    print(f"Uploading {upload_file} ...")
    name = config["name"].capitalize()
    title = f"{name} - Humans of TIKS"
    description = instagram_caption(config)
    cover_image = os.path.abspath(f'IGTV-{config["cover"]["image"]}')
    upload_to_instagram(upload_file, cover_image, title, description)


if __name__ == "__main__":
    cli(obj={})
