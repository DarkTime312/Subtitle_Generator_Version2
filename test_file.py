import ffmpeg
import whisper
import argparse
import warnings
import tempfile
from utils import filename, str2bool, write_srt
import tkinter as tk
from tkinter import ttk
import threading
from whisper.transcribe import my_variable_proxy
from tkinter import filedialog
from tkinter import messagebox
import pathlib
import sys
import os


def resource_path(relative_path):
    """ Get the absolute path to the resource, works for dev and PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS2
    except Exception:
        base_path = os.path.abspath("auto_subtitle")
    return os.path.join(base_path, relative_path)


def select_file():
    global video_path
    video_path = filedialog.askopenfilenames(filetypes=(('MP4 Files', '*.mp4'), ('All files', '*.*')))
    file_path_var.set(video_path[0] if len(video_path) == 1 else 'Multiple files!')


def start_task():
    # Start the long-running task in a separate thread
    start = threading.Thread(target=convert)
    start.start()


def convert():
    args['model'] = model_var.get()
    args['video'] = [file for file in video_path]
    file = pathlib.Path(video_path[0])
    args['output_dir'] = str(file.parent)
    main()


def main():
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("video", nargs="+", type=str,
                        help="paths to video files to transcribe")
    parser.add_argument("--model", default="tiny.en",
                        choices=whisper.available_models(), help="name of the Whisper model to use")
    parser.add_argument("--output_dir", "-o", type=str,
                        default=".", help="directory to save the outputs")
    parser.add_argument("--output_srt", type=str2bool, default=False,
                        help="whether to output the .srt file along with the video files")
    parser.add_argument("--srt_only", type=str2bool, default=False,
                        help="only generate the .srt file and not create overlayed video")
    parser.add_argument("--verbose", type=str2bool, default=False,
                        help="whether to print out the progress and debug messages")

    parser.add_argument("--task", type=str, default="transcribe", choices=[
        "transcribe", "translate"],
                        help="whether to perform X->X speech recognition ('transcribe') or X->English translation ('translate')")
    parser.add_argument("--language", type=str, default="auto",
                        choices=["auto", "af", "am", "ar", "as", "az", "ba", "be", "bg", "bn", "bo", "br", "bs", "ca",
                                 "cs", "cy", "da", "de", "el", "en", "es", "et", "eu", "fa", "fi", "fo", "fr", "gl",
                                 "gu", "ha", "haw", "he", "hi", "hr", "ht", "hu", "hy", "id", "is", "it", "ja", "jw",
                                 "ka", "kk", "km", "kn", "ko", "la", "lb", "ln", "lo", "lt", "lv", "mg", "mi", "mk",
                                 "ml", "mn", "mr", "ms", "mt", "my", "ne", "nl", "nn", "no", "oc", "pa", "pl", "ps",
                                 "pt", "ro", "ru", "sa", "sd", "si", "sk", "sl", "sn", "so", "sq", "sr", "su", "sv",
                                 "sw", "ta", "te", "tg", "th", "tk", "tl", "tr", "tt", "uk", "ur", "uz", "vi", "yi",
                                 "yo", "zh"],
                        help="What is the origin language of the video? If unset, it is detected automatically.")

    model_name: str = args.pop("model")
    output_dir: str = args.pop("output_dir")
    output_srt: bool = args.pop("output_srt")
    srt_only: bool = args.pop("srt_only")
    language: str = args.pop("language")

    os.makedirs(output_dir, exist_ok=True)

    if model_name.endswith(".en"):
        warnings.warn(
            f"{model_name} is an English-only model, forcing English detection.")
        args["language"] = "en"
    # if translate task used and language argument is set, then use it
    elif language != "auto":
        args["language"] = language

    model = whisper.load_model(model_name)
    audios = get_audio(args.pop("video"))
    subtitles = get_subtitles(
        audios, output_srt or srt_only, output_dir,
        lambda audio_path: model.transcribe(audio_path, verbose=False, **args)
    )

    if srt_only:
        return

    for path, srt_path in subtitles.items():
        out_path = os.path.join(output_dir, f"{filename(path)}.mp4")

        print(f"Adding subtitles to {filename(path)}...")

        video = ffmpeg.input(path)
        audio = video.audio

        ffmpeg.concat(
            video.filter('subtitles', srt_path, force_style="OutlineColour=&H40000000,BorderStyle=3"), audio, v=1, a=1
        ).output(out_path).run(quiet=True, overwrite_output=True)

        print(f"Saved subtitled video to {os.path.abspath(out_path)}.")
        # print(args)


def add_progress():
    global progress
    if my_variable_proxy.content is None:
        root.after(5, add_progress)
    else:
        progress_var = tk.IntVar()
        # print(my_variable_proxy.content, my_variable_proxy.seek)

        progress = ttk.Progressbar(root, mode='determinate', maximum=my_variable_proxy.content, variable=progress_var, length=300)
        progress.pack(pady=50)

        def update():
            # print(content_frames, seek)
            # print(my_variable_proxy.content, my_variable_proxy.seek)
            if my_variable_proxy.seek is not None:
                progress_var.set(my_variable_proxy.seek)
            if progress_var.get() != my_variable_proxy.content:
                root.after(10, update)

        update()


def get_audio(paths):
    temp_dir = tempfile.gettempdir()

    audio_paths = {}

    for path in paths:
        print(f"Extracting audio from {filename(path)}...")
        output_path = os.path.join(temp_dir, f"{filename(path)}.wav")

        ffmpeg.input(path).output(
            output_path,
            acodec="pcm_s16le", ac=1, ar="16k"
        ).run(quiet=True, overwrite_output=True)

        audio_paths[path] = output_path

    return audio_paths


def get_subtitles(audio_paths: list, output_srt: bool, output_dir: str, transcribe: callable):
    subtitles_path = {}

    root.attributes('-disabled', True)
    for path, audio_path in audio_paths.items():
        add_progress()
        print(path, audio_path)
        srt_path = output_dir if output_srt else tempfile.gettempdir()
        srt_path = os.path.join(srt_path, f"{filename(path)}.srt")

        print(
            f"Generating subtitles for {filename(path)}... This might take a while."
        )

        warnings.filterwarnings("ignore")
        result = transcribe(audio_path)
        warnings.filterwarnings("default")

        with open(srt_path, "w", encoding="utf-8") as srt:
            write_srt(result["segments"], file=srt)

        subtitles_path[path] = srt_path
        progress.pack_forget()
        progress.update_idletasks()
        print('Should be destroyed')
        my_variable_proxy.content = None
        my_variable_proxy.seek = None
    # When all file are processed
    root.attributes('-disabled', False)
    progress.pack_forget()
    messagebox.showinfo("Done", "Done!")

    return subtitles_path


args = {'model': 'tiny.en',
        'output_dir': r"G:\Udemy\Python\Doing now\Tkinter\Udemy - Learn Python by creating 10 apps with tkinter 2023-10\0 - Done\1. Introduction\New folder",
        'output_srt': True,
        'srt_only': True,
        'language': 'en',
        'video': [
            r'G:\Udemy\Python\Doing now\Tkinter\Udemy - Learn Python by creating 10 apps with tkinter 2023-10\0 - Done\1. Introduction\New folder\1. Trailer.mp4']
        }

root = tk.Tk()
root.geometry('500x500')
root.title("Sub generator")

theme_path = resource_path('Azure/azure.tcl')
root.tk.call('source', theme_path)
root.tk.call("set_theme", "light")

select_path_btn = ttk.Button(root, text='Select Files', command=select_file)
file_path_var = tk.StringVar()
lbl_path = ttk.Label(root, textvariable=file_path_var)

model_var = tk.StringVar(value='tiny.en')

rb_frm = ttk.Frame(root)
rb_lbl = ttk.Label(rb_frm, text='Select Model:')

rb1 = ttk.Radiobutton(rb_frm, text='Tiny', value='tiny.en', variable=model_var)
rb2 = ttk.Radiobutton(rb_frm, text='Small', value='small.en', variable=model_var)
rb3 = ttk.Radiobutton(rb_frm, text='Medium', value='medium.en', variable=model_var)

btn_convert = ttk.Button(root, text='Convert', command=start_task)

status_label = ttk.Label(root, text='')
status_label.pack()

progress = ttk.Progressbar(root, length=200, mode='determinate')

# layout:
select_path_btn.pack(pady=20)
lbl_path.pack()
rb_lbl.pack(side='left', padx=20)
rb1.pack(anchor='w')
rb2.pack(anchor='w')
rb3.pack(anchor='w')
rb_frm.pack(pady=50)

btn_convert.pack()

root.mainloop()
