import caw.widget
import collections
import re
import itertools
import operator
import math

class CPU(caw.widget.Widget):
    """
    CPU widget for getting statistics of processor time

    This is an example of a widget that has a global updator rather than a single one.  In other
    words, the class functions update all interfaces and then set the values of class instances
    based on what interface has been updated.  This way the file is read once per update rather
    than mulitple times per update.

    Parameters
    -----------

    fg : alias for normal_fg

    normal_border : normal foreground for the cpu stat

    medium_fg : foreground for cpu when medium is met

    high_fg : foreground for cpu when the high is met

    medium : medium threshold

    high : high threshold

    """

    _initialized = False
    _widgets = collections.defaultdict(list)

    def __init__(self, cpu=0, fg=None, medium_fg=0xffff00, high_fg=0xff0000, medium=40, high=80, show_percent=False, **kwargs):
        super(CPU, self).__init__(**kwargs)
        self.cpu = cpu
        self.normal_fg = kwargs.get('normal_fg', fg)
        self.medium_fg = medium_fg
        self.high_fg = high_fg
        self.medium = medium
        self.high = high
        self.show_percent = show_percent

    def init(self, parent):
        super(CPU, self).init(parent)
        self.data = collections.defaultdict(int)

        if not CPU._initialized:
            CPU._clsinit(self.parent)

        CPU._widgets[self.cpu].append(self)

    @classmethod
    def _clsinit(cls, parent):
        cls._re = re.compile('^cpu')
        cls._sep = re.compile('[ *]*')
        cls._file = open('/proc/stat', 'r')
        cls._cache = {}
        cls._parent = parent

        cls._update(0)

        cls._initialized = True

    @classmethod
    def _update(cls, timeout=3):
        cls._file.seek(0)
        i = 0
        cache = cls._cache
        #print "cpu:_update"
        for line in cls._file:
            if cls._re.match(line):
                info = cls._sep.split(line)
                active = reduce(operator.add, itertools.imap(int, info[1:4]))
                total = active + int(info[4])

                try:
                    difftotal = total - cache[i]['total']
                    diffactive = active - cache[i]['active']
                    cache[i]['usage'] = math.floor((float(diffactive) / difftotal) * 100)
                except KeyError:
                    cache[i] = {}
                except ZeroDivisionError:
                    cache[i]['usage'] = 0

                cache[i]['total'] = total
                cache[i]['active'] = active

                for w in cls._widgets.get(i, []):
                    w.data = cache[i]
                    w.parent.update()

                i += 1

        cls._parent.schedule(timeout, cls._update)

    def _get_data(self):
        return self._data

    def _set_data(self, data):
        self._data = data
        if self.show_percent:
            self.width_hint = self.parent.text_width("%d%%" % self._data['usage'])
        else:
            self.width_hint = self.parent.text_width("%d" % self._data['usage'])

    data = property(_get_data, _set_data)

    def draw(self):
        val = self._data['usage']
        fg = self.normal_fg
        if val > self.high:
            fg = self.high_fg
        elif val > self.medium:
            fg = self.medium_fg

        if self.show_percent:
            self.parent.draw_text("%d%%" % self._data['usage'], fg=fg)
        else:
            self.parent.draw_text("%d" % self._data['usage'], fg=fg)



