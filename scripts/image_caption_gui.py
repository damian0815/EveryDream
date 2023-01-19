# Python GUI tool to manually caption images for machine learning.
# A sidecar file is created for each image with the same name and a .txt extension.
#
# [control/command + o] to open a folder of images.
# [page down] and [page up] to go to next and previous images. Hold shift to skip 10 images.
# [shift + home] and [shift + end] to go to first and last images.
# [shift + delete] to move the current image into a '_deleted' folder.
# [escape] to exit the app.

import sys
import tkinter as tk
import traceback
from random import random
from tkinter import filedialog
from typing import Generator

from PIL import Image, ImageTk

# enchant needs PYENCHANT_LIBRARY_PATH=/opt/homebrew/lib/libenchant-2.2.dylib
import os
os.environ["PYENCHANT_LIBRARY_PATH"]="/opt/homebrew/lib/libenchant-2.2.dylib"
from enchant import Dict, tokenize

from pathlib import Path

IMG_EXT = ["jpg", "jpeg", "png"]

class CaptionedImage():
    def __init__(self, image_path):
        self.base_path = image_path.parent
        self.path = image_path
    
    def caption_path(self):
        return self.base_path / (self.path.stem + '.txt')

    def read_caption(self):
        caption_path = self.caption_path()
        if caption_path.exists():
            with open(caption_path, 'r', encoding='utf-8', newline='') as f:
                return f.read()
        return ''

    def write_caption(self, caption):
        caption_path = self.caption_path()
        with open(str(caption_path), 'w', encoding='utf-8', newline='') as f:
            f.write(caption)
    
    # sort
    def __lt__(self, other):
        return str(self.path).lower() < str(other.path).lower()

# adapted from https://stackoverflow.com/a/66281314
class SpellcheckText(tk.Text):
    locale = 'en_US'
    def __init__(self, master, **kwargs):
        self.afterid = None
        self.corpus = Dict(self.locale)
        self.tokenize = tokenize.get_tokenizer(self.locale)
        super(SpellcheckText, self).__init__(master, **kwargs)
        self._proxy = self._w + "_proxy"
        self.tk.call("rename", self._w, self._proxy)
        self.tk.createcommand(self._w, self._proxycmd)
        self.tag_configure('sic', foreground='red')
        self.bind('<<TextModified>>', self.on_modify)

    def _proxycmd(self, command, *args):
        """Intercept the Tk commands to the text widget and if eny of the content
        modifying commands are called, post a TextModified event."""
        # avoid error when copying
        if command == 'get' \
                and (args[0] == 'sel.first' and args[1] == 'sel.last') \
                and not self.tag_ranges('sel'):
            return

        # avoid error when deleting
        if command == 'delete'\
                and (args[0] == 'sel.first' and args[1] == 'sel.last') \
                and not self.tag_ranges('sel'):
            return

        cmd = (self._proxy, command)
        if args:
            cmd = cmd + args
        try:
            result = self.tk.call(cmd)
        except tk.TclError:
            traceback.print_exc()
            return
        if command in ('insert', 'delete', 'replace'):
            self.event_generate('<<TextModified>>')
        return result

    def on_modify(self, event):
        """Rate limit the spell-checking with a 500ms delay. If another modification
        event comes in within this time, cancel the after call and re-schedule."""
        try:
            delay = 200 # ms
            if self.afterid:
                self.after_cancel(self.afterid)
            self.afterid = self.after(delay, self.on_modified)
        except Exception as e:
            print(e)

    def on_modified(self):
        """Handle the spell check once modification pauses.
        The tokenizer works on lines and yields a list of (word, column) pairs
        So iterate over the words and set a sic tag on each spell check failed word."""
        self.afterid = None
        self.tag_remove('sic', '1.0', 'end')
        num_lines = [int(val) for val in self.index("end").split(".")][0]
        for line in range(1, num_lines):
            data = self.get(f"{line}.0 linestart", f"{line}.0 lineend")
            for word,pos in self.tokenize(data):
                check = self.corpus.check(word)
                #print(f"{word},{pos},{check}")
                if not check:
                    start = f"{line}.{pos}"
                    end = f"{line}.{pos + len(word)}"
                    self.tag_add("sic", start, end)


class ImageView(tk.Frame):

    def __init__(self, root):
        tk.Frame.__init__(self, root)

        self.root = root
        self.base_path = None
        self.images = []
        self.index = 0
        self.search_text = ''

        # image
        self.image_frame = tk.Frame(self)
        self.image_label = tk.Label(self.image_frame)
        self.image_label.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
        self.image_frame.pack(expand=True, fill=tk.BOTH, side=tk.LEFT)
        
        # caption field
        self.caption_frame = tk.Frame(self)
        self.caption_field = SpellcheckText(
            self.caption_frame, wrap="word", width=40,
                                            font=('Courier', 16),
                                            undo=True, autoseparators=True)
        self.caption_field.pack(expand=True, fill=tk.BOTH)
        self.caption_frame.pack(fill=tk.Y, side=tk.RIGHT)

    def open_folder(self):
        dir = filedialog.askdirectory()
        if not dir:
            return
        self.base_path = Path(dir)
        if self.base_path is None:
            return
        self.images.clear()
        for directory, _, filenames in os.walk(dir):
            image_filenames = [f for f in filenames if os.path.splitext(f)[1] in IMG_EXT]
            for filename in image_filenames:
                self.images.append(CaptionedImage(Path(os.path.join(directory,filename))))
        self.images.sort()
        self.update_ui()

    def shuffle_images(self):
        self.store_caption()
        random.shuffle(self.images)
        self.set_index(0)
        self.update_ui()

    def store_caption(self):
        txt = self.caption_field.get(1.0, tk.END)
        txt = txt.replace('\r', '').replace('\n', '').strip()
        self.images[self.index].write_caption(txt)
        
    def set_index(self, index):
        self.index = index % len(self.images)

    def go_to_image(self, index):
        if len(self.images) == 0:
            return
        self.store_caption()
        self.set_index(index)
        self.update_ui()

    def next_image(self):
        self.go_to_image(self.index + 1)

    def prev_image(self):
        self.go_to_image(self.index - 1)

    # move current image to a "_deleted" folder
    def delete_image(self):
        if len(self.images) == 0:
            return
        img = self.images[self.index]

        trash_path = self.base_path / '_deleted'
        if not trash_path.exists():
            trash_path.mkdir()
        img.path.rename(trash_path / img.path.name)
        caption_path = img.caption_path()
        if caption_path.exists():
            caption_path.rename(trash_path / caption_path.name)
        del self.images[self.index]
        self.set_index(self.index)
        self.update_ui()
    
    def update_ui(self):
        if (len(self.images)) == 0:
            self.filename.set('')
            self.caption_field.delete(1.0, tk.END)
            self.image_label.configure(image=None)
            return
        img = self.images[self.index]
        # filename
        title = self.images[self.index].path.name if len(self.images) > 0 else ''
        self.root.title(title + f' ({self.index+1}/{len(self.images)})')
        # caption
        self.caption_field.edit_reset()
        self.caption_field.edit_modified()
        self.caption_field.delete(1.0, tk.END)
        self.caption_field.insert(tk.END, img.read_caption())
        self.caption_field.edit_reset()
        # image
        img = Image.open(self.images[self.index].path)
        
        # scale the image to fit inside the frame
        w = self.image_frame.winfo_width()
        h = self.image_frame.winfo_height()
        if img.width > w or img.height > h:
            img.thumbnail((w, h))
        photoImage = ImageTk.PhotoImage(img)
        self.image_label.configure(image=photoImage)
        self.image_label.image = photoImage

    def open_find_ui(self, reverse=False):
        title = "Find in captions"
        prompt = "Enter a text string to find in captions:"
        self.search_text = tk.simpledialog.askstring(title, prompt)
        print("searching for", self.search_text)
        if reverse:
            self.find_prev()
        else:
            self.find_next()

    def load_all_captions(self) -> Generator[str, None, None]:
        for i in self.images:
            yield i.read_caption()

    def find_next(self):
        if len(self.images) == 0:
            return
        if len(self.search_text) == 0:
            self.open_find_ui()
        else:
            start_index = ((self.index+1) % len(self.images))
            end_index = len(self.images)
            self.find_next_internal(start_index, end_index, reverse=False)

    def find_prev(self):
        if len(self.images) == 0:
            return
        if len(self.search_text) == 0:
            self.open_find_ui(reverse=True)
        else:
            # prev search is just a next search with the indices reversed
            end_index = (self.index+len(self.images)-1) % len(self.images)
            start_index = 0
            self.find_next_internal(start_index, end_index, reverse=True)

    def find_next_internal(self, start_index, end_index, reverse=False, wrap=True):
        print(f"find_next_internal from {start_index} to {end_index}, reverse:{reverse}, wrap:{wrap}")
        captions = list(self.load_all_captions())
        if start_index >= end_index:
            raise ValueError(f"start index {start_index} must be < end index {end_index}")
        try:
            print('searching ')
            indices = range(start_index, end_index)
            if reverse:
                indices = reversed(indices)
            next_index = next(i for i in indices if self.search_text in captions[i])
            print(f"going to {next_index}")
            self.go_to_image(next_index)
        except StopIteration:
            # loop, but don't loop forever
            if wrap:
                if reverse:
                    self.find_next_internal(start_index=end_index, end_index=len(self.images), reverse=True, wrap=False)
                else:
                    self.find_next_internal(start_index=0, end_index=start_index, reverse=False, wrap=False)


if __name__=='__main__':
    root = tk.Tk()
    root.geometry('1200x800')
    root.title('Image Captions')

    if sys.platform == 'darwin':
        root.bind('<Command-o>', lambda e: view.open_folder())
        root.bind('<Command-f>', lambda e: view.open_find_ui())
        root.bind('<Command-g>', lambda e: view.find_next())
        root.bind('<Command-h>', lambda e: view.find_prev())
    else:
        root.bind('<Control-o>', lambda e: view.open_folder())
        root.bind('<Control-f>', lambda e: view.open_find_ui())
        root.bind('<Control-g>', lambda e: view.find_next())
        root.bind('<Control-h>', lambda e: view.find_prev())
    root.bind('<Escape>', lambda e: root.destroy())
    root.bind('<Prior>', lambda e: view.prev_image())
    root.bind('<Next>', lambda e: view.next_image())
    root.bind('<Shift-Prior>', lambda e: view.go_to_image(view.index - 10))
    root.bind('<Shift-Next>', lambda e: view.go_to_image(view.index + 10))
    root.bind('<Shift-Home>', lambda e: view.go_to_image(0))
    root.bind('<Shift-End>', lambda e: view.go_to_image(len(view.images) - 1))
    root.bind('<Shift-Delete>', lambda e: view.delete_image())
    root.bind('<Command-l>', lambda e: view.shuffle_images())

    view = ImageView(root)
    view.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
    root.mainloop()