import caw.widget
import time

class Clock(caw.widget.Widget):
    def __init__(self, format="%Y.%m.%d %H:%M:%S", fg=None, **kwargs):
        super(Clock, self).__init__(**kwargs)
        self.format = format
        self.fg = fg

    def init(self, parent):
        super(Clock, self).init(parent)
        self.update()

    def update(self):
        self.text = time.strftime(self.format)
        self.width_hint = self.parent.text_width(self.text)
        self.parent.update(self);
        self.parent.schedule(1, self.update)

    def draw(self):
        self.parent.draw_text(self.text, fg=self.fg)

