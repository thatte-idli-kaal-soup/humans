# Humans of TIKS

Repository with tools for creating the Humans of TIKS videos.

The videos can be found [here](https://www.youtube.com/playlist?list=PLo98-81j1ocKx7DsxOYNavJx9vmcL0oWx).

# Software Installation and Usage

## Installation

-   We use `ffmpeg` to do all the heavy lifting for us. Make sure that you have
    `ffmpeg` on your PATH. You can download it from
    [here](https://www.ffmpeg.org/download.html)

-   To install the requirements for the tool, install the requirements.

```sh
pip install -r requirements.txt
```

## Usage

The script `./scripts/process-video.py` does all the automation that we need.
Run the script to see some help.

```sh
python script/process-video.py --help
```

### Editing Process

1.  Copy the videos to a sub-directory in the `media` directory, and create an
    empty `.yml` config file in the `projects` directory. For example,
    `media/vk` with the videos, and an empty `projects/vk.yml`.

1.  Run the `populate-config` command to start populating the empty template,
    and also convert videos to low resolution videos. It is easier to work with
    lower resolution videos, while you are figuring out what to keep and what to
    remove. Once you are happy with content, you can generate the high
    resolution videos.

1.  Start creating the edited video, by watching the recording and selecting
    clips that you want to keep. See other existing `.yml` files to see the
    format for each clip. It should have a question, and some timings from the
    video to select/pick.

    A clip can be made up of multiple segments. Each segment has a start time
    and an end time. The segments can come from the same video or different
    videos. Each segment can specify the video that it comes from, using a
    `video` key. Each segment can also specify a `crop` to specify which part of
    the original video's frame should be cropped to make this segment.

1.  Always specify the videos using their high-res names. The processing script
    automatically chooses the high-res or the low res video based on whether the
    `--use-original` or `--use-low-res` flag is passed.

1.  You can add a crop value to the file or to each clip or segment, to crop the
    video to a square one. The crop value looks something like `ih:ih:ih/3.2:0`.
    The parameters are `width:height:width_offset:height_offset`. `width` and
    `height` define the bounding box you are using to crop the video.
    `width_offset` and `height_offset`, define where to place the box on the
    original video. `ih` and `iw` are height and width of the original video.

1.  You can use the `process-clips` command to process and produce a short clip
    for each specific question. For example, the following command will process
    the 4th question in `vk.yml`.

    ```sh
    ./scripts/process-video.py projects/vk.yml process-clips -n4
    ```

    Adding the `--with-intro` flag adds the question/answer video at the
    beginning of the clip.

1.  To find the number of a question you want to process, you can use the
    `print-index` command.

    ```tsv
    No.	Question & Answer	Duration (s)	Q time (s)
    1	How did you start playing Ultimate?	33.1	4
    2	What sports did you play before and how does it compare to Ultimate?	63.9	5
    3	How was the experience of cycling from Manali to Leh?	77.6	4
    4	What keeps you playing Ultimate?	13.4	4
    ```

1.  You can specify the background music to use for the video using the `bgm`
    key. Similarly, you can also specify the `cover` image to use and the
    `credits` slide for the video.

1.  To generate the full video from the clips, use the `combine-clips`
    sub-command. For example, the following command will generate the complete
    video using the configuration specified in `aishu.yml`.

    ```sh
    ./scripts/process-video.py projects/aishu.yml combine-clips
    ```

    This will generate the video in the aspect ratio required for IGTV too,
    along with a simple square video.

1.  Once you are happy with all the segments and clips and the complete video,
    you can generated the high-res video using the same two commands as above,
    `process-clips` and `combine-clips`, but with the additional
    `--use-original` flag passed to the commands.

    ```sh
    ./scripts/process-video.py --use-original projects/aishu.yml process-clips
    ./scripts/process-video.py --use-original projects/aishu.yml combine-clips
    ```

    You can also use the helper script `generate.sh` to do this.

    ```sh
    ./generate.sh aishu --use-original
    ```

1.  Upload the `IGTV-ALL-music-*` video to IGTV and use the `IGTV-cover.jpg` as
    the cover image. You can upload the `ALL-music-*` video to YouTube. Use the
    low-res videos when uploading testing versions to get feedback from the
    person giving the interview, and the rest of the team. Use the high res
    videos when uploading for the real audience.

# Notes for the "Human of TIKS"

-   This is just a conversation, where we are trying to get to know you and your
    journey with Ultimate.
-   We'd like to have a free-wheeling conversation with you, where you share
    everything that matters to you! Don't feel obliged to stay on topic or
    answer questions succintly.
-   Obviously, we are only going to publish things from the conversation, that
    you are comfortable sharing with the "world". We'll ask you to review the
    edited version of this conversation, before we publish it.
-   Use your phone to record your video.
-   Make sure you have enough space on your phone to be able to record for half
    an hour to an hour. You'll need about 3-4GB of space if you are recording at
    1920x1080. We can also record via Zoom, if that is not possible for you.
-   Record the video in landscape mode.
-   Put your phone in airplane more or in DND mode for the next hour or so.
-   Make sure there is adequate lighting where you are sitting.
-   Make sure you are sitting so that you appear in roughly the same portion of
    the screen , for most part of the video. This would make it easier to
    crop/edit for Instagram.
-   Try doing a sample recording of the video. (Use the template question for
    this)
-   Avoid using swear words, if possible. We'd like to be able to post the video
    for Ultimate players in all age groups.
-   Use gender-neutral language/pronouns wherever you can. Use they/them or
    she/her instead of saying he/him/his. Person-D not Man-D. etc.
-   Use headphones for talking over video chat. Hearing sounds of pings on your
    computer, or other people typing, makes the audio quality poor.
-   Ensure that your headphones are charged, if they are bluetooth headphones.
-   It would help to have a bottle of water handy. :)

# Checklists

## Interview Preparation

-   Shortlist next people to interview
-   Contact them and fix a time for the interview
-   Share Video Recording checklist with them
-   Prepare questions, ask team mates/instagram for questions
-   Do the interview and collect the video for editing

## Video Publishing

-   [ ] Get pictures from interviewee to make poster. Work on the poster.
-   [ ] Get a go ahead from the interviewee if the content and poster are okay!
-   [ ] Decide on whether to make a trailer, and post it.
-   [ ] Write post description
-   [ ] Figure out hashtags (if any changes are required from the last post)
-   [ ] If there are "code" changes that potentially change how audio/video
        streams are made, try posting from a trial account to verify Instagram
        doesn't mess up anything. **NOTE**: Do verify on an iDevice!
-   [ ] Make the actual post!
-   [ ] Upload on YouTube and share on the group.

# Ideas/Suggestions for improvement

Some ideas and suggestions provided by various people, that we could try to
incorporate in future videos. Ideally, our tool should incorporate these
features, rather than us adding anything manually.

-   [ ] Captions on videos may be nice, especially when the audio is noisy.
