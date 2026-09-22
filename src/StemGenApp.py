#!/usr/bin/python3
# Main
# if __name__ == '__main__':from PyQt5.uic import loadUi

import os
import sys
import traceback

from PyQt5.QtCore import Qt, QThread, pyqtSlot
from PyQt5.QtGui import QCursor
from PyQt5.QtWidgets import QApplication, QFileDialog, QMainWindow

from layout import Ui_MainWindow
from runtime import augmented_path

# Must run before `stemgen` is imported: torch probes the environment at
# import time and StemGen.setup() looks ffmpeg/sox up on PATH. A bundle
# launched from Finder gets launchd's PATH, which has no Homebrew in it.
os.environ["PATH"] = augmented_path()

from stemgen import StemGen


class StemThread(QThread):
    
    def __init__(self, tracks):
        super().__init__()
        self.stemgen = StemGen()
        self.tracks = tracks

    def run(self):
        self.stemgen.run(self.tracks)


# Main Window
class MainWindow(QMainWindow, Ui_MainWindow):

    def __init__(self):
        super().__init__()
        self.stem_thread = None
        
        self.setupUi(self)

        self.start_button.pressed.connect(self.start)
        self.close.clicked.connect(self.exitprogram)
        
    @pyqtSlot()
    def start(self):
        # Native OS file picker (Finder sheet / Explorer dialog), filtered to
        # the formats the pipeline accepts — see StemGen.supported_files.
        tracks, _ = QFileDialog.getOpenFileNames(
            self,
            "Select tracks to convert to stems",
            "",
            "Audio files (*.wav *.wave *.aif *.aiff *.flac *.mp3);;All files (*)",
        )
        if tracks:
            try:
                if self.stem_thread is not None:
                    return
                self.stem_thread = StemThread(tracks)
                self.stem_thread.finished.connect(self.thread_finished)  
                self.stem_thread.stemgen.song_processing.connect(self.update_song_processing) 
                self.stem_thread.stemgen.counts.connect(self.update_counters)
                self.stem_thread.stemgen.details_update.connect(self.details_update)
                self.stem_thread.start()
            
            except ValueError as e:
                print(e)
                print(traceback.format_exc())
                self.statusMsg.setText(str(e))

    def thread_finished(self):
        self.stem_thread.deleteLater()  # Clean up the thread properly
        self.stem_thread = None

    @pyqtSlot(str)
    def details_update(self, details):
        self.details.setText(details)

    @pyqtSlot(str)
    def update_song_processing(self, song_name):
        self.song_name.setText(song_name)

    @pyqtSlot(str, int, int, int, int)
    def update_counters(self, status, total, downloaded, skipped, failed):
        if skipped != 0 or failed != 0:
            self.counter_label.setText(status+":\t" + str(downloaded+skipped+failed) + "/" + str(total)  + "\tprocessed:" + str(downloaded) + "\tskipped: " + str(skipped) + "\tfailed:" + str(failed))
        else:
            self.counter_label.setText(status+":\t" + str(downloaded+failed+skipped) + "/" + str(total) )
    

    # DRAGGLESS INTERFACE

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.m_drag = True
            self.m_DragPosition = event.globalPos() - self.pos()
            event.accept()
            self.setCursor(QCursor(Qt.ClosedHandCursor))

    def mouseMoveEvent(self, QMouseEvent):
        if Qt.LeftButton and self.m_drag:
            self.move(QMouseEvent.globalPos() - self.m_DragPosition)
            QMouseEvent.accept()

    def mouseReleaseEvent(self, QMouseEvent):
        self.m_drag = False
        self.setCursor(QCursor(Qt.ArrowCursor))

    def exitprogram(self):
        sys.exit()


# Main
if __name__ == '__main__':
    import multiprocessing

    # Order matters on Python >= 3.13: freeze_support() resolves the default
    # context, after which set_start_method() raises "context has already
    # been set". Pick spawn first (so Linux matches macOS/Windows and the
    # frozen build never forks a Qt process), then let freeze_support() do
    # its Windows-bundle dance.
    multiprocessing.set_start_method('spawn')
    multiprocessing.freeze_support()
    
    app = QApplication(sys.argv)
    Screen = MainWindow()
    Screen.setFixedWidth(740)
    Screen.setFixedHeight(620)
    Screen.setWindowFlags(Qt.FramelessWindowHint)
    Screen.setAttribute(Qt.WA_TranslucentBackground)
    Screen.show()
    sys.exit(app.exec())


