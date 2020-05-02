#!/usr/bin/env python3

import argparse
import os
import subprocess


def to_seconds(timestamp):
    times = [float(x) for x in timestamp.split(".", 1)]
    return times[0] * 60 + times[1]


def main(video_path, timings):
    video_name = os.path.basename(video_path)
    for i, line in enumerate(timings, start=1):
        start, end = line.split("-")
        start_seconds = to_seconds(start)
        end_seconds = to_seconds(end)
        print(start_seconds, end_seconds)
        duration = end_seconds - start_seconds
        subprocess.call(
            [
                "ffmpeg",
                "-y",
                "-i",
                video_name,
                "-ss",
                str(start_seconds),
                "-t",
                str(duration),
                f"part-{i}-{video_name}",
            ],
            cwd=os.path.dirname(video_path),
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("video_file", type=str)
    parser.add_argument("timings", type=open)
    options = parser.parse_args()
    video_path = os.path.abspath(options.video_file)
    main(video_path, options.timings)
