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

TODO: Add more description of each of the sub commands

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
-   Record the video in portrait mode.
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
        doesn't mess up anything.
-   [ ] Make the actual post!
-   [ ] Upload on YouTube and share on the group.

# Ideas/Suggestions for improvement

Some ideas and suggestions provided by various people, that we could try to
incorporate in future videos. Ideally, our tool should incorporate these
features, rather than us adding anything manually.

-   [ ] Add an outro slide?
-   [ ] See if we can embed video/pictures of people playing/practicing
-   [ ] Figure out best time to post based on when our audience is online.
-   [ ] Captions on videos may be nice, especially when the audio is noisy.
