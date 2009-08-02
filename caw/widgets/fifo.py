import caw.widget
import os
import stat
import operator
from itertools import imap, izip

class FIFO(caw.widget.Widget):
    def __init__(self, filename, align="right", start_color=0xff0000, end_color=0x999999, steps=10, variable_width=True, **kwargs):
        super(FIFO, self).__init__(**kwargs)
        self.filename = filename
        self.text = ''
        self.file = None
        self.align = align
        self.text_width = 0
        if variable_width:
            self.width_hint = -1
        else:
            self.width_hint = self.text_width

        self.colors = [end_color]
        self.coloridx = 0

        srgb = (start_color >> 16,
                start_color >> 8 & 0xff,
                start_color & 0xff)

        ergb = (end_color >> 16,
                end_color >> 8 & 0xff,
                end_color & 0xff)

        step = [ (s - e) / (steps -1) for s,e in izip(srgb, ergb) ]

        curcolor = ergb[:]
        for i in xrange(steps-2):
            curcolor = [ c+s for c,s in izip(curcolor, step)]
            color = reduce(operator.ior, (curcolor[0] << 16,
                    curcolor[1] << 8,
                    curcolor[2]))
            self.colors.append(color)
        self.colors.append(start_color)

    def init(self, parent):
        self.parent = parent
        if not os.path.exists(self.filename):
            print "File does not exist:", self.filename
            return

        if not stat.S_ISFIFO(os.stat(self.filename).st_mode):
            print "Not a FIFO:", self.filename
            return

        self.fd = os.open(self.filename, os.O_RDONLY | os.O_NONBLOCK)
        self.parent.registerfd(self.fd, self.update)

    def update(self, eventmask):
        self.parent.unregisterfd(self.fd)
        file = os.fdopen(self.fd)

        txt = file.read().strip().split('\n')
        if txt:
            self.text = txt[-1]

        self.fd = os.open(self.filename, os.O_RDONLY | os.O_NONBLOCK)
        self.parent.registerfd(self.fd, self.update)

        self.text_width = self.parent.text_width(self.text)

        if self.width_hint >= 0:
            self.width_hint = self.text_width

        self.coloridx = len(self.colors) -1

        self.parent.update()
        self.parent.schedule(1, self.update_coloridx)

    def update_coloridx(self):
        self.coloridx -= 1
        self.parent.update()

        if self.coloridx > 0:
            self.parent.schedule(1, self.update_coloridx)

    def draw(self):
        x = self.x

        if self.align=="right":
            x += self.width - self.text_width

        if self.align=="center":
            x += (self.width + self.text_width) / 2

        self.parent.draw_text(self.text, self.colors[self.coloridx], x)


