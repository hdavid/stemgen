#!/usr/bin/python3
# Main
# if __name__ == '__main__':from PyQt5.uic import loadUi

from PyQt5.QtWidgets import QMainWindow, QApplication, QFileDialog
from PyQt5.QtCore import Qt, QThread, pyqtSignal, pyqtSlot
from PyQt5.QtGui import  QCursor
from layout import Ui_MainWindow

import sys
import os
import platform
import string
import re
import traceback

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
        super(MainWindow, self).__init__()
        self.stem_thread = None
        
        self.setupUi(self)

        self.start_button.pressed.connect(self.start)
        self.close.clicked.connect(self.exitprogram)
        
    @pyqtSlot()
    def start(self):
        options = QFileDialog.Options()
        options |= QFileDialog.DontUseNativeDialog
        tracks, _ = QFileDialog.getOpenFileNames(self,"QFileDialog.getOpenFileNames()", "","All Files (*)", options=options)
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
    
    multiprocessing.freeze_support()
    multiprocessing.set_start_method('spawn')
    
    app = QApplication(sys.argv)
    Screen = MainWindow()
    Screen.setFixedWidth(740)
    Screen.setFixedHeight(620)
    Screen.setWindowFlags(Qt.FramelessWindowHint)
    Screen.setAttribute(Qt.WA_TranslucentBackground)
    Screen.show()
    sys.exit(app.exec())


