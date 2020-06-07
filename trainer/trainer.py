#!/usr/bin/env python3
# vim:set et sts=4 sw=4:
#
# Abalone Trainer - Fine tunes speech recognition models for individual users
#
# Copyright (c) 2020 Mike Sheldon <elleo@gnu.org>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gst", "1.0")
from gi.repository import Gtk, GObject, GLib, Gio, Gst
from xdg import BaseDirectory
import os, os.path
import threading
import random
import glob

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
        self.training_dir = os.path.join(self.data_dir, "training-data")
        if not os.path.exists(self.training_dir):
            os.mkdir(self.training_dir)
        self.model_total_size = 0
        self.scorer_total_size = 0
        self.current_model_downloaded = 0
        self.current_scorer_downloaded = 0

        self.downloads = 0

        self.have_sample = False

        # Clean up incomplete downloads
        if os.path.exists(self.model_file + ".part"):
            os.remove(self.model_file + ".part")

        if os.path.exists(self.scorer_file + ".part"):
            os.remove(self.scorer_file + ".part")

        self.window = self.builder.get_object("trainer")
        self.progress_bar = self.builder.get_object("download_progress")
        self.tuning_page = self.builder.get_object("tuning_page")
        self.play_button = self.builder.get_object("play_button")
        self.sentence_buffer = self.builder.get_object("sentence")
        self.sentences = self.load_sentences()
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

    def load_sentences(self):
        sentences = []
        for sentence_file in glob.glob("training-text/*.txt"):
            f = open(sentence_file, 'r')
            sentences += f.readlines()
            f.close()
        return sentences

    def update_training_sentence(self):
        self.have_sample = False
        self.play_button.set_sensitive(False)
        self.sentence_buffer.set_text(random.choice(self.sentences))

    def on_record_button_toggled(self, button):
        pass

    def on_play_button_toggled(self, button):
        pass

    def on_next_sentence_button_clicked(self, *args):
        self.update_training_sentence()

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
        if page == self.tuning_page:
            self.update_training_sentence()



if __name__ == "__main__":
    trainer = Trainer()	
    Gtk.main()