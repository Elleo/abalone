#!/usr/bin/env python3
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GObject, GLib, Gio
from xdg import BaseDirectory
import os, os.path
import threading


MODEL_URL = "http://abalone-data.mikeasoft.com/deepspeech-0.7.1-models.pbmm"
SCORER_URL = "http://abalone-data.mikeasoft.com/deepspeech-0.7.1-models.scorer"

class Trainer:

    def __init__(self):
        self.builder = Gtk.Builder()
        self.builder.add_from_file("trainer.glade")
        self.builder.connect_signals(self)
        self.data_dir = BaseDirectory.save_data_path("abalone")
        self.model_file = os.path.join(self.data_dir, "deepspeech-0.7.1-models.pbmm")
        self.scorer_file = os.path.join(self.data_dir, "deepspeech-0.7.1-models.scorer")
        self.model_total_size = 0
        self.scorer_total_size = 0
        self.current_model_downloaded = 0
        self.current_scorer_downloaded = 0

        self.downloads = 0

        # Clean up incomplete downloads
        if os.path.exists(self.model_file + ".part"):
            os.remove(self.model_file + ".part")

        if os.path.exists(self.scorer_file + ".part"):
            os.remove(self.scorer_file + ".part")

        self.window = self.builder.get_object("trainer")
        self.progress_bar = self.builder.get_object("download_progress")
        self.window.show_all()

    def download_progress(self, current_num_bytes, total_num_bytes, download_id):
        if download_id == "model":
            self.model_total_size = total_num_bytes
            self.current_model_downloaded = current_num_bytes
        elif download_id == "scorer":
            self.scorer_total_size = total_num_bytes
            self.current_scorer_downloaded = current_num_bytes
        self.progress_bar.set_fraction((self.current_model_downloaded + self.current_scorer_downloaded) / (self.model_total_size + self.scorer_total_size))

    def download_complete(self, source_object, res, download_id):
        if download_id == "model":
            os.rename(self.model_file + ".part", self.model_file)
        elif download_id == "scorer":
            os.rename(self.scorer_file + ".part", self.scorer_file)
        self.downloads -= 1
        if self.downloads == 0:
            self.progress_bar.set_text("Download complete")
            self.window.set_page_complete(self.progress_bar, True)

    def on_trainer_close(self, *args):
        Gtk.main_quit()

    def on_trainer_apply(self, *args):
        print(args)

    def on_trainer_prepare(self, assistant, page):
        if page == self.progress_bar:
            if self.downloads == 0 and os.path.exists(self.model_file) and os.path.exists(self.scorer_file):
                self.progress_bar.set_fraction(1)
                self.progress_bar.set_text("Download complete")
                self.window.set_page_complete(page, True)
            else:
                if not os.path.exists(self.model_file) and not os.path.exists(self.model_file + ".part"):
                    model_downloader = Gio.File.new_for_uri(MODEL_URL)
                    model_downloader.copy_async(Gio.File.new_for_path(self.model_file + ".part"), Gio.FileCopyFlags.OVERWRITE, GLib.PRIORITY_DEFAULT, None, self.download_progress, ("model",), self.download_complete, ("model",))
                    self.downloads += 1
                if not os.path.exists(self.scorer_file) and not os.path.exists(self.scorer_file + ".part"):
                    scorer_downloader = Gio.File.new_for_uri(SCORER_URL)
                    scorer_downloader.copy_async(Gio.File.new_for_path(self.scorer_file + ".part"), Gio.FileCopyFlags.OVERWRITE, GLib.PRIORITY_DEFAULT, None, self.download_progress, ("scorer",), self.download_complete, ("scorer",))
                    self.downloads += 1


if __name__ == "__main__":
    trainer = Trainer()	
    Gtk.main()
