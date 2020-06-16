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

1. Create a directory with the name that matches with the `.yml` file. For
   example, a directory `vk` with the videos, and create an empty `vk.yml` at
   the top level of the repository.

1. Run the `populate-config` command to create the empty template, and also
   convert videos to low resolution videos. It is easier to work with lower
   resolution videos, while you are figuring out what to keep and what to
   remove. Once you are happy with content, you can generate the high resolution
   videos.

1. Start creating the edited video, by watching the recording and selecting
   clips that you want to keep. See other existing `.yml` files to see the
   format for each clip. It should have a question, and some timings from the
   video to select/pick.

1. You can use the `process-clips` command to process and produce a short clip
   for each specific question. For example, the following command will process
   the 4th question in `vk.yml`.

    ```sh
    ./scripts/process-video.py vk.yml process-clips -n4
    ```

1. To find the number of a question you want to process, you can use the
   `print-index` command.

    ```tsv
    No.	Question & Answer	Duration (s)	Q time (s)
    1	How did you start playing Ultimate?	33.1	4
    2	What sports did you play before and how does it compare to Ultimate?	63.9	5
    3	How was the experience of cycling from Manali to Leh?	77.6	4
    4	What keeps you playing Ultimate?	13.4	4
    ```

1. You can add a crop value to the file, to crop the video to a square one. The
   crop value looks something like `ih:ih:ih/3.2:0`. The parameters are
   `width:height:width_offset:height_offset`. `width` and `height` define the
   bounding box you are using to crop the video. `width_offset` and
   `height_offset`, define where to place the box on the original video. `ih`
   and `iw` are height and width of the original video.
   

TODO: More description needs to be added for the rest of the process...

# Checklists

## Interview Preparation

-   Shortlist next people to interview
-   Contact them and fix a time for the interview
-   Share Video Recording checklist with them
-   Prepare questions, ask team mates/instagram for questions
-   Do the interview and collect the video for editing

## Video Recording

-   Use your phone to record your video.
-   Make sure you have enough space on your phone to be able to record for half
    an hour to an hour. You'll need about 3-4GB of space if you are recording at
    1920x1080. We can also record via Zoom, if that is not possible for you.
-   Put your phone in airplane more or in DND mode for the next hour or so.
-   Record the video in landscape mode.
-   Make sure there is adequate lighting where you are sitting.
-   Make sure you are sitting so that you appear in roughly the same portion of
    the screen , for most part of the video. This would make it easier to
    crop/edit for Instagram.
-   Try doing a sample recording of the video. (Use the template question for
    this)
-   Avoid using swear words, if possible. We'd like to be able to post the video
    for Ultimate players in all age groups.
-   Use headphones for talking over video chat. Hearing sounds of pings on your
    computer, or other people typing, makes the audio quality poor.
-   Ensure that your headphones are charged, if they are bluetooth headphones.
-   Have a bottle of water next to you.

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

-   [ ] Add an outro slide?
-   [ ] See if we can embed video/pictures of people playing/practicing
-   [ ] Captions on videos may be nice, especially when the audio is noisy.
