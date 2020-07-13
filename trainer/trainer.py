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
import jiwer
import glob
import sys

MODEL_URL = "http://abalone-data.mikeasoft.com/deepspeech-0.7.1-models.pbmm"
SCORER_URL = "http://abalone-data.mikeasoft.com/deepspeech-0.7.1-models.scorer"
CHECKPOINT_URL = "http://abalone-data.mikeasoft.com/deepspeech-0.7.1-checkpoint.tar.gz"
MIN_SAMPLES_REQUIRED = 10

class Trainer:

    def __init__(self):
        self.builder = Gtk.Builder()
        self.builder.add_from_file("trainer.glade")
        self.builder.connect_signals(self)
        self.data_dir = BaseDirectory.save_data_path("abalone")
        self.model_file = os.path.join(self.data_dir, "deepspeech-0.7.1-models.pbmm")
        self.scorer_file = os.path.join(self.data_dir, "deepspeech-0.7.1-models.scorer")
        self.checkpoint_file = os.path.join(self.data_dir, "deepspeech-0.7.1-checkpoint.tar.gz")
        self.training_dir = os.path.join(self.data_dir, "training-data")
        
        self.sample_id = 0
        if not os.path.exists(self.training_dir):
            os.mkdir(self.training_dir)
        else:
            for wav_file in glob.glob(os.path.join(self.training_dir, "*.wav")):
                wav_id = int(wav_file[:-4].split("/")[-1])
                if wav_id >= self.sample_id:
                    self.sample_id = wav_id + 1

        self.model_total_size = 0
        self.scorer_total_size = 0
        self.checkpoint_total_size = 0
        self.current_model_downloaded = 0
        self.current_scorer_downloaded = 0
        self.current_checkpoint_downloaded = 0

        self.downloads = 0

        self.have_sample = False

        if os.path.exists(os.path(self.training_dir, "training.csv")):
            self.training_csv = open(os.path(self.training_dir, "training.csv"), "a")
        else:
            self.training_csv = open(os.path(self.training_dir, "training.csv"), "w")
            self.training_csv.write("wav_filename,wav_filesize,transcript")
        if os.path.exists(os.path(self.training_dir, "testing.csv")):
            self.testing_csv = open(os.path(self.training_dir, "testing.csv"), "a")
        else:
            self.testing_csv = open(os.path(self.training_dir, "testing.csv"), "w")

        # Clean up incomplete downloads
        if os.path.exists(self.model_file + ".part"):
            os.remove(self.model_file + ".part")

        if os.path.exists(self.scorer_file + ".part"):
            os.remove(self.scorer_file + ".part")

        if os.path.exists(self.checkpoint_file + ".part"):
            os.remove(self.checkpoint_file + ".part")

        self.init_recording()
        self.init_playback()

        self.window = self.builder.get_object("trainer")
        self.download_progress = self.builder.get_object("download_progress")
        self.training_progress = self.builder.get_object("training_progress")
        self.download_page = self.builder.get_object("download_page")
        self.tuning_page = self.builder.get_object("tuning_page")
        self.training_page = self.builder.get_object("training_page")
        self.record_button = self.builder.get_object("record_button")
        self.play_button = self.builder.get_object("play_button")
        self.sentence_buffer = self.builder.get_object("sentence")
        self.sentences = self.load_sentences()
        self.window.show_all()

        self.test_text = ""
        self.recognised_text = ""

        self.pretraining = False
        self.training = False
        self.posttraining = False

    def update_download_progress(self, current_num_bytes, total_num_bytes, download_id):
        if download_id == "model":
            self.model_total_size = total_num_bytes
            self.current_model_downloaded = current_num_bytes
        elif download_id == "scorer":
            self.scorer_total_size = total_num_bytes
            self.current_scorer_downloaded = current_num_bytes
        elif download_id == "checkpoint":
            self.checkpoint_total_size = total_num_bytes
            self.current_checkpoint_downloaded = current_num_bytes
        self.download_progress.set_fraction((self.current_model_downloaded + self.current_scorer_downloaded + self.current_checkpoint_downloaded) / (self.model_total_size + self.scorer_total_size + self.checkpoint_total_size))

    def download_complete(self, source_object, res, download_id):
        if download_id == "model":
            os.rename(self.model_file + ".part", self.model_file)
        elif download_id == "scorer":
            os.rename(self.scorer_file + ".part", self.scorer_file)
        elif download_id == "checkpoint":
            os.rename(self.checkpoint_file + ".part", self.checkpoint_file)
        self.downloads -= 1
        if self.downloads == 0:
            self.download_progress.set_text("Download complete")
            self.window.set_page_complete(self.download_progress, True)

    def update_sentence_count(self):
        sentence_count = self.builder.get_object("sentence_count")
        sentence_count.set_text("%d/%d" % (self.sample_id, MIN_SAMPLES_REQUIRED))
        if self.sample_id >= MIN_SAMPLES_REQUIRED:
            self.window.set_page_complete(self.tuning_page, True)

    def load_sentences(self):
        sentences = []
        for sentence_file in glob.glob("training-text/*.txt"):
            f = open(sentence_file, 'r')
            sentences += f.readlines()
            f.close()
        return sentences

    def update_training_sentence(self):
        if self.have_sample:
            self.sample_id += 1
        self.have_sample = False
        self.play_button.set_sensitive(False)
        self.sentence_buffer.set_text(random.choice(self.sentences))
        self.update_sentence_count()

    def init_recording(self):
        self.record_pipeline = Gst.parse_launch("autoaudiosrc ! audioconvert ! audiorate ! audioresample ! audio/x-raw,format=S16LE,rate=16000,channels=1 ! wavenc ! filesink name=wavrecfile")
        self.wavrecfile = self.record_pipeline.get_by_name("wavrecfile")

    def init_playback(self):
        self.play_pipeline = Gst.parse_launch("filesrc name=wavplayfile ! decodebin ! audioconvert ! autoaudiosink")
        self.wavplayfile = self.play_pipeline.get_by_name("wavplayfile")
        bus = self.play_pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self.on_playback_message)

    def test_sample(self, sample_to_test):
        self.testing_sample = sample_to_test
        self.test_pipeline = Gst.parse_launch("filesrc name=wavtestfile ! decodebin ! audioconvert ! audiorate ! audioresample ! deepspeech silence-threshold=1 silence-length=20 name=deepspeech ! fakesink")
        deepspeech = self.test_pipeline.get_by_name("deepspeech")
        deepspeech.set_property("speech-model", self.model_file)
        deepspeech.set_property("scorer", self.scorer_file)
        f = open(os.path.join(self.training_dir, "%d.txt" % sample_to_test), 'r')
        self.test_text += f.read()
        f.close()
        self.wavtestfile = self.test_pipeline.get_by_name("wavtestfile")
        self.wavtestfile.set_property("location", os.path.join(self.training_dir, "%d.wav" % sample_to_test))
        bus = self.test_pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self.on_test_message)
        self.test_pipeline.set_state(Gst.State.PLAYING)

    def reset_recording(self):
        self.record_button.set_active(False)
        self.record_pipeline.set_state(Gst.State.NULL)
        self.init_recording()

    def reset_playback(self):
        self.play_button.set_active(False)
        self.play_pipeline.set_state(Gst.State.NULL)
        self.init_playback()

    def on_playback_message(self, bus, message):
        if message.type == Gst.MessageType.EOS:
            self.reset_playback()

    def on_test_message(self, bus, message):
        structure = message.get_structure()
        if structure and structure.get_name() == "deepspeech" and structure.get_value("intermediate") == False:
            self.recognised_text += structure.get_value("text") + "\n"
            self.training_progress.set_fraction((self.testing_sample + 1) / self.sample_id)
            if self.testing_sample < self.sample_id - 1:
                self.test_pipeline.set_state(Gst.State.NULL)
                self.test_sample(self.testing_sample + 1)
            else:
                self.test_text = jiwer.RemovePunctuation()(self.test_text).lower().encode("ascii", "ignore").decode()
                print("Expected:", self.test_text)
                print("Got:", self.recognised_text)
                accuracy = 100 - jiwer.wer(self.test_text.replace("\n", " "), self.recognised_text.replace("\n", " ").replace("'", "")) * 100
                if self.pretraining:
                    pretraining_accuracy_label = self.builder.get_object("pretraining_accuracy_label")
                    pretraining_accuracy_label.set_text("%.2f%%" % accuracy)
                    self.pretraining = False
                    self.training = True
                    status_label = self.builder.get_object("status_label")
                    status_label.set_text("Training...")
                    self.training_progress.set_fraction(0)
                if self.posttraining:
                    posttraining_accuracy_label = self.builder.get_object("posttraining_accuracy_label")
                    posttraining_accuracy_label.set_text("%.2f%%" % accuracy)
                    spinner = self.builder.get_object("spinner")
                    spinner.set_active = False
                    self.posttraining = False

    def on_record_button_toggled(self, button):
        if button.get_active():
            self.reset_playback()
            f = open(os.path.join(self.training_dir, "%d.txt" % self.sample_id), 'w')
            f.write(self.sentence_text)
            f.close()
            self.wavrecfile.set_property("location", os.path.join(self.training_dir, "%d.wav" % self.sample_id))
            training_file = os.path.join("Deepspeech", "training-data", "%d.wav" % self.sample_id)
            stripped_text = jiwer.RemovePunctuation()(self.sentence_text).lower().encode("ascii", "ignore").decode().replace("'", "")
            wavsize = os.stat(location).st_size
            if self.sample_id % 6 < 3:
                # Training sample
                self.training_csv.write("%s,%d,%s" % (training_file, wavsize, stripped_text))
            else:
                # Testing sample
                self.testing_csv.write("%s,%d,%s" % (training_file, wavsize, stripped_text))
            self.record_pipeline.set_state(Gst.State.PLAYING)
            self.play_button.set_sensitive(True)
            self.have_sample = True
        else:
            self.reset_recording()

    def on_play_button_toggled(self, button):
        if button.get_active():
            self.reset_recording()
            self.wavplayfile.set_property("location", os.path.join(self.training_dir, "%d.wav" % self.sample_id))
            self.play_pipeline.set_state(Gst.State.PLAYING)
        else:
            self.reset_playback()

    def on_next_sentence_button_clicked(self, *args):
        self.play_pipeline.set_state(Gst.State.READY)
        self.record_pipeline.set_state(Gst.State.READY)
        self.update_training_sentence()

    def on_trainer_close(self, *args):
        Gtk.main_quit()

    def on_trainer_apply(self, *args):
        print(args)

    def on_trainer_prepare(self, assistant, page):
        if page == self.download_page:
            if self.downloads == 0 and os.path.exists(self.model_file) and os.path.exists(self.scorer_file) and os.path.exists(self.checkpoint_file):
                self.download_progress.set_fraction(1)
                self.download_progress.set_text("Download complete")
                self.window.set_page_complete(page, True)
            else:
                if not os.path.exists(self.model_file) and not os.path.exists(self.model_file + ".part"):
                    model_downloader = Gio.File.new_for_uri(MODEL_URL)
                    model_downloader.copy_async(Gio.File.new_for_path(self.model_file + ".part"), Gio.FileCopyFlags.OVERWRITE, GLib.PRIORITY_DEFAULT, None, self.update_download_progress, ("model",), self.download_complete, ("model",))
                    self.downloads += 1
                if not os.path.exists(self.scorer_file) and not os.path.exists(self.scorer_file + ".part"):
                    scorer_downloader = Gio.File.new_for_uri(SCORER_URL)
                    scorer_downloader.copy_async(Gio.File.new_for_path(self.scorer_file + ".part"), Gio.FileCopyFlags.OVERWRITE, GLib.PRIORITY_DEFAULT, None, self.update_download_progress, ("scorer",), self.download_complete, ("scorer",))
                    self.downloads += 1
                if not os.path.exists(self.checkpoint_file) and not os.path.exists(self.checkpoint_file + ".part"):
                    checkpoint_downloader = Gio.File.new_for_uri(CHECKPOINT_URL)
                    checkpoint_downloader.copy_async(Gio.File.new_for_path(self.checkpoint_file + ".part"), Gio.FileCopyFlags.OVERWRITE, GLib.PRIORITY_DEFAULT, None, self.update_download_progress, ("checkpoint",), self.download_complete, ("checkpoint",))
                    self.downloads += 1
        if page == self.tuning_page:
            self.update_training_sentence()
        if page == self.training_page:
            if not self.pretraining and not self.training and not self.posttraining:
                self.pretraining = True
                self.test_sample(0)

    @property
    def sentence_text(self):
        startIter, endIter = self.sentence_buffer.get_bounds()    
        return self.sentence_buffer.get_text(startIter, endIter, False) 



if __name__ == "__main__":
    Gst.init(sys.argv)
    trainer = Trainer()	
    Gtk.main()
