#!/usr/bin/python

import cawc
import select
import collections
import xcb
import xcb.xproto as xproto
import struct
import array

import time
import re
import math
import operator
import itertools
import heapq

try:
    import alsaaudio
except ImportError:
    alsaaudio = None
import ossaudiodev

class Widget(object):
    def __init__(self):
        super(Widget, self).__init__()
        self.width = 0
        self.x = 0
        self.min_width = 0
        self.parent = None

    def buttonpress(self, button, x):
        pass

    def setup(self):
        pass

    def draw(self):
        pass

class Clock(Widget):
    def __init__(self, format="%Y.%m.%d %H:%M:%S", color=None):
        super(Clock, self).__init__()
        self.format = format
        self.color = color

    def setup(self):
        self.update()

    def update(self):
        self.text = time.strftime(self.format)
        self.min_width = self.parent.text_width(self.text)
        self.parent.update();
        self.parent.schedule(1, self.update)

    def draw(self):
        self.parent.draw_text(self.text, color=self.color)

class Desktop(Widget):
    def __init__(self, current_fg=None, fg=None, showall=False):
        self.desktops = []
        self.current = 0
        self.fg = fg
        self.current_fg = current_fg
        self.fg = fg
        self.showall = showall

    def setup(self):
        print "setup"
        a = self.parent.get_atoms([
            "_NET_CURRENT_DESKTOP",
            "_NET_WM_DESKTOP",
            "_NET_DESKTOP_NAMES",
            "UTF8_STRING",
            "_NET_NUMBER_OF_DESKTOPS"])

        for key,val in a.iteritems():
            setattr(self, key, val)

        self.parent.atoms[self._NET_WM_DESKTOP].append(self._update)
        self.parent.atoms[self._NET_CURRENT_DESKTOP].append(self._update)
        self.parent.atoms[self._NET_DESKTOP_NAMES].append(self._get_desktops)
        self._get_desktops()
        #if self.fg is None:
        #    self.fg = self.parent.fg
        #if self.current_fg is None:
        #    self.current_fg = self.parent.fg

        #if self.current_bg is not None or self.bg is not None:
        #    self.gc = self.parent.root.create_gc()

    def _get_desktops(self):
        print "get desk"
        conn = self.parent.connection
        scr = self.parent.screen
        totalc = conn.core.GetProperty(0,
                scr.root,
                self._NET_NUMBER_OF_DESKTOPS,
                xcb.XA_CARDINAL,
                0,
                12)

        namesc = conn.core.GetProperty(0,
                scr.root,
                self._NET_DESKTOP_NAMES,
                self.UTF8_STRING,
                0,
                32)

        totalr = totalc.reply()
        self.num_desktops = struct.unpack_from("I", totalr.value.buf())[0]

        namesr = namesc.reply()
        self.desktops = struct.unpack_from("%ds" % namesr.value_len, 
                namesr.value.buf())[0].strip("\x00").split("\x00")

        self._update()

    def _output(self):
        out = ""
        if self.showall:
            return ' '.join(self.desktops)
        else:
            return self.desktops[self.current]


    def _update(self, event=None):
        conn = self.parent.connection
        scr = self.parent.screen
        currc = conn.core.GetProperty(0, scr.root, self._NET_CURRENT_DESKTOP,
                xcb.XA_CARDINAL, 0, 12)
        currp = currc.reply()
        self.current = struct.unpack_from("I", currp.value.buf())[0]
        self.min_width = self.parent.text_width(self._output())
        self.parent.update()


    def draw(self):
        color = self.fg
        curx = self.x
        if self.showall:
            last = len(self.desktops) - 1
            for i, name in enumerate(self.desktops):
                if i == self.current:
                    color = self.current_fg
                else:
                    color = self.fg

                if i != 0:
                    self.parent.draw_text(' ')
                self.parent.draw_text(name, color=color)

        else:
            self.parent.draw_text(self.desktops[self.current], color=self.current_fg)

class Volume(Widget):
    def __init__(self, device='Master', med=30, high=70, step=1, driver='alsa', percent_color=None):
        super(Volume, self).__init__()
        self.device = device
        self.med = med
        self.high = high
        self.step = step
        self.percent_color = percent_color
        if driver == 'alsa' and alsaaudio is None :
            driver = 'oss'

        self.driver = driver

    def setup(self):
        getattr(self, '_init_' + self.driver)()
        self.min = 0
        self.max = 100

        self.fglow = 0xcccccc
        self.fgmed = 0x00cc00
        self.fghigh = 0xcc0000
        self._update()

    def _init_oss(self):
        self.device_mask = getattr(ossaudiodev, "SOUND_MIXER_%s" % self.device.upper(), None)
        if self.device_mask is None:
            self.device_mask = getattr(ossaudiodev, "SOUND_MIXER_VOLUME")

        self.mixer = ossaudiodev.openmixer()

    def _init_alsa(self):
        self.mixer = alsaaudio.Mixer(self.device)
        self.min, self.max = self.mixer.getrange()

    def _update_alsa(self):
        vol = alsaaudio.Mixer(self.device).getvolume()
        self.current = reduce(operator.add, vol) / len(vol)
        self.percent = round((float(self.current) / self.max) * 100)

    def _update_oss(self):
        vol = self.mixer.get(self.device_mask)
        self.current = reduce(operator.add, vol) / len(vol)
        self.percent = round((float(self.current) / self.max) * 100)

    def _update(self):
        getattr(self, "_update_" + self.driver)()
        self.min_width = self.parent.text_width("%d%%" % self.percent)
        self.parent.schedule(2, self._update)

    def draw(self):
        fg = self.fglow
        if self.percent > self.high:
            fg = self.fghigh
        elif self.percent > self.med:
            fg = self.fgmed

        self.parent.draw_text("%d" % self.percent, self.x, fg)
        self.parent.draw_text("%", color=self.percent_color)

    def _set_alsa(self, value):
        alsaaudio.Mixer(self.device).setvolume(value)

    def _set_oss(self, value):
        self.mixer.set(self.device_mask, (value,value))

    def buttonpress(self, button, x):
        if button == 5:
            newval =  max(self.current-self.step, self.min)
            getattr(self, "_set_" + self.driver)(newval)
            getattr(self, "_update_" + self.driver)()
            self.parent.redraw()
        elif button == 4:
            newval =  min(self.current+self.step, self.max)
            getattr(self, "_set_" + self.driver)(newval)
            getattr(self, "_update_" + self.driver)()
            self.parent.redraw()


class Systray(Widget):
    def __init__(self, spacing=2):
        super(Systray, self).__init__()
        self.spacing=spacing

    def setup(self, icon_size=None):
        self.icon_size = icon_size
        if icon_size is None:
            if self.parent.height >= 24:
                self.icon_size = 24
            elif self.parent.height >= 16:
                self.icon_size = 16
            else:
                self.icon_size = self.parent.height

        self.tasks = {}

        conn = self.parent.connection
        scr = self.parent.screen
        self.parent.events[xproto.ClientMessageEvent].append(self._clientmessage)
        self.parent.events[xproto.ConfigureNotifyEvent].append(self._configurenotify)
        self.parent.events[xproto.DestroyNotifyEvent].append(self._destroynotify)

        a = self.parent.get_atoms([
            "_NET_SYSTEM_TRAY_OPCODE",
            "_NET_SYSTEM_TRAY_S%d" % 0,
            "MANAGER",
            "WM_STATE"
            ])

        for key,val in a.iteritems():
            print key, val
            setattr(self, key, val)

        self.window = conn.generate_id()
        conn.core.CreateWindow(scr.root_depth,
                self.window, self.parent.window,
                -1, -1, 1, 1, 0,
                xproto.WindowClass.CopyFromParent,
                scr.root_visual,
                0,
                [])

        print "Systray window:", self.window

        # have to manually build the event!
        response_type = 33 # XCB_CLIENT_MESSAGE
        format = 32
        sequence = 0
        window = scr.root
        type = self.MANAGER
        data = [xcb.CurrentTime, self._NET_SYSTEM_TRAY_S0, self.window, 0, 0]
        event = struct.pack('BBHII5I', response_type, format, sequence, window, type, xcb.CurrentTime, self._NET_SYSTEM_TRAY_S0, self.window, 0, 0)

        e = conn.core.SetSelectionOwnerChecked(self.window, self._NET_SYSTEM_TRAY_S0, xcb.CurrentTime)
        e = conn.core.SendEventChecked(0, scr.root, 0xffffff, event)


    def _destroynotify(self, event):
        print "********* DESTROY NOTIFY **************"
        if event.window in self.tasks:
            conn = self.parent.connection
            del self.tasks[event.window]
            self.min_width=self.icon_size*len(self.tasks)+ self.spacing * (len(self.tasks)-1)

    def _clientmessage(self, event):
        if event.window == self.window:
            print "!!!!!!!!!!!!! CLIENT MESSAGE !!!!!!!!!!!!!!!"
            opcode = xproto.ClientMessageData(event, 0, 20).data32[2]
            data = xproto.ClientMessageData(event, 12, 20)
            task = data.data32[2]
            if opcode == self._NET_SYSTEM_TRAY_OPCODE:
                conn = self.parent.connection

                #conn.core.ChangeProperty(xproto.PropMode.Replace, task, self.WM_STATE, self.WM_STATE, 32, 2, struct.pack('II', 0, 0))

                conn.core.ReparentWindow(task, self.parent.window, 0, 0)
                conn.core.ChangeWindowAttributes(task, xproto.CW.EventMask, [xproto.EventMask.Exposure|xproto.EventMask.StructureNotify])
                conn.flush()
                self.tasks[task] = dict(x=0, y=0, width=self.icon_size, height=self.icon_size)
                self.min_width=self.icon_size*len(self.tasks)+ self.spacing * (len(self.tasks)-1)
                self.parent.update()

    def _configure_window(self, window, x, y, w, h):
        x = int(x)
        y = int(y)
        w = int(w)
        h = int(h)

        cawc.xcb_configure_window(self.parent.connection_c,
                window, x, y, w, h)
        return

        #self.parent.connection.core.ConfigureWindow(
        #        window, 
        #        (xproto.ConfigWindow.X |
        #        xproto.ConfigWindow.Y |
        #        xproto.ConfigWindow.Width |
        #        xproto.ConfigWindow.Height),
        #        struct.pack('IIIIIII', x,y,w,h,0,0,0))

    def _configurenotify(self, event):
        print "********* CONFIGURE NOTIFY **************"
        if event.window in self.tasks:
            print 'HERES OUR WINDOW!'
            task = self.tasks[event.window]
            conn = self.parent.connection
            self._configure_window(event.window,
                    task['x'], task['y'],
                    task['width'], task['height'])
            #conn.core.ChangeWindowAttributes(event.window, xproto.CW.EventMask, [xproto.EventMask.StructureNotify])

    def draw(self):
        curx = self.x

        conn = self.parent.connection
        width = max(self.min_width, 1)
        #self._configure_window(self.window, curx, 0, width, self.parent.height)
        #conn.core.ClearArea(0, self.window, 0, 0, width, self.parent.height)
        #conn.core.MapWindow(self.window)

        for taskwin in self.tasks:
            task = self.tasks[taskwin]
            task['x'] = curx
            task['y'] = (self.parent.height - task['height'])/2
            print "CONFIGURE"
            self._configure_window(taskwin,
                    task['x'], task['y'],
                    task['width'], task['height'])
            print "MAP"
            conn.core.MapWindow(taskwin)
            conn.flush()
            curx += task['width'] + self.spacing


class Spacer(Widget):
    def __init__(self, width=5):
        super(Spacer, self).__init__()
        self.min_width = width

class Text(Widget):
    def __init__(self, text="undefined", color=None):
        super(Text, self).__init__()
        self.text = text
        self.color = color

    def setup(self):
        self.min_width = self.parent.text_width(self.text)
        print self.min_width

    def draw(self):
        self.parent.draw_text(self.text, self.x, self.color)

class CPU(Widget):
    _initialized = False
    _widgets = collections.defaultdict(list)

    def __init__(self, cpu=0, fg_color=None, med_color=0xffff00, high_color=0xff0000, med_threshold=40, high_threshold=80, percent_color=None):
        super(CPU, self).__init__()
        self.cpu = cpu
        self.fg_color = fg_color
        self.med_color = med_color
        self.high_color = high_color
        self.med_threshold = med_threshold
        self.high_threshold = high_threshold
        self.percent_color = percent_color

    def setup(self):
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
        for line in cls._file:
            if cls._re.match(line):
                info = cls._sep.split(line)
                active = reduce(operator.add, itertools.imap(int, info[1:4]))
                total = active + int(info[4])

                try:
                    difftotal = total - cls._cache[i]['total']
                    diffactive = active - cls._cache[i]['active']
                    cls._cache[i]['usage'] = math.floor((float(diffactive) / difftotal) * 100)
                except KeyError:
                    cls._cache[i] = {}
                except ZeroDivisionError:
                    cls._cache[i]['usage'] = 0

                cls._cache[i]['total'] = total
                cls._cache[i]['active'] = active

                for w in cls._widgets.get(i, []):
                    w.data = cls._cache[i]
                    w.parent.update()

                i += 1

        cls._parent.schedule(timeout, cls._update)

    def _get_data(self):
        return self._data

    def _set_data(self, data):
        self._data = data
        self.min_width = self.parent.text_width("%d%%" % self._data['usage'])

    data = property(_get_data, _set_data)

    def draw(self):
        val = self._data['usage']
        color = self.fg_color
        if val > self.high_threshold:
            color = self.high_color
        elif val > self.med_threshold:
            color = self.med_color
        self.parent.draw_text("%d" % self._data['usage'], color=color)
        self.parent.draw_text("%", color=self.percent_color)


class Caw:
    def __init__(self, font_face='Terminus', font_size=8, fg_color = 0x000000, bg_color=0xd6d6d6, border_color=0x606060, shading=100, border_width=2, height=10, edge=1):
        self.connection_c = cawc.xcb_connect()
        self.screen_c = cawc.xcb_screen(self.connection_c)
        self.visualtype_c = cawc.xcb_visualtype(self.screen_c)

        self.connection = xcb.wrap(self.connection_c)
        self.screen = self.connection.get_setup().roots[0]

        self.border_width = border_width
        self.height = height + 2*self.border_width
        self.width = self.screen.width_in_pixels
        self.x = 0
        if edge:
            self.y = self.screen.height_in_pixels - self.height
        else:
            self.y = 0

        self.fg_color = fg_color
        self.bg_color = bg_color
        self.border_color = border_color
        self.shading = shading

        self.font_face = font_face
        self.font_size = font_size

        self.left = []
        self.right = []
        self._timers = []
        self.events = collections.defaultdict(list)
        self.atoms = collections.defaultdict(list)
        self._update = False

        self._init_window()
        self._init_atoms()
        self._root_pixmap()
        self._init_cairo()

        print "Window:", self.window
        print self.x
        print self.y
        print self.width
        print self.height
        print self.connection.core.GetWindowAttributes(self.window)
        self._set_properties()
        self._update_struts()

        self.connection.core.MapWindow(self.window)
        cawc.xcb_configure_window(self.connection_c, self.window, self.x, self.y, self.width, self.height)
        self.connection.flush()

        self.events[xproto.ExposeEvent].append(self.redraw)
        self.events[xproto.PropertyNotifyEvent].append(self._property_notify)
        self.events[xproto.ButtonPressEvent].append(self._button_press)
        self.atoms[self._XROOTPMAP_ID].append(self._update_background)


    def get_atoms(self, atoms):
        conn = self.connection

        # get all the atoms we need
        cookies = []
        for a in atoms:
            cookies.append(conn.core.InternAtom(False,len(a),a))

        ret = {}

        # get the replies (properly)
        for c,a in zip(cookies, atoms):
            ret[a] = c.reply().atom

        return ret

    def _init_window(self):
        conn = self.connection
        scr = self.screen
        self.back_pixmap = conn.generate_id()
        conn.core.CreatePixmap(scr.root_depth,
                self.back_pixmap, scr.root,
                self.width, self.height)

        self.window = conn.generate_id()
        conn.core.CreateWindow(scr.root_depth,
                self.window, scr.root,
                self.x, self.y,
                self.width, self.height,
                0,
                xproto.WindowClass.InputOutput,
                scr.root_visual,
                xproto.CW.BackPixmap | xproto.CW.EventMask,
                [self.back_pixmap,
                    xproto.EventMask.Exposure |
                    xproto.EventMask.EnterWindow |
                    xproto.EventMask.ButtonPress |
                    xproto.EventMask.ButtonRelease]
                )

        self._gc = conn.generate_id()
        conn.core.CreateGC(self._gc, self.window,
                xproto.GC.Foreground | xproto.GC.Background,
                [scr.white_pixel, scr.black_pixel])

    def _init_cairo(self):
        self._back_cairo_c = cawc.cairo_create(
                self.connection_c,
                self.back_pixmap,
                self.visualtype_c,
                self.width,
                self.height)

        self.cairo_c = cawc.cairo_create(
                self.connection_c,
                self.window,
                self.visualtype_c,
                self.width,
                self.height)

        cawc.cairo_select_font_face(self.cairo_c, self.font_face)
        cawc.cairo_set_font_size(self.cairo_c, self.font_size)
        self._font_height = cawc.cairo_font_height(self.cairo_c)

    def _init_atoms(self):
        a = self.get_atoms([
                "_NET_WM_WINDOW_TYPE", 
                "_NET_WM_WINDOW_TYPE_DOCK", 
                "_NET_WM_DESKTOP",
                "_NET_WM_STATE",
                "_NET_WM_STATE_SKIP_PAGER",
                "_NET_WM_STATE_SKIP_TASKBAR",
                "_NET_WM_STATE_STICKY",
                "_NET_WM_STATE_ABOVE",
                "_NET_WM_STRUT",
                "_NET_WM_STRUT_PARTIAL",
                "_WIN_STATE",
                "_XROOTPMAP_ID",
                ])
        for key,val in a.iteritems():
            setattr(self, key, val)

    def _root_pixmap(self):
        conn = self.connection
        scr = self.screen
        cookie = conn.core.GetProperty(False, scr.root, self._XROOTPMAP_ID,
                xcb.XA_PIXMAP, 0, 10)

        rep = cookie.reply()
        return struct.unpack_from("I", rep.value.buf())[0]

    def _set_properties(self):
        conn = self.connection
        scr = self.screen
        win = self.window

        conn.core.ChangeProperty(xproto.PropMode.Replace, win, xcb.XA_WM_NAME, xcb.XA_STRING, 8, len("CAW!"), "CAW!")

        conn.core.ChangeProperty(xproto.PropMode.Replace, win, xcb.XA_WM_CLASS, xcb.XA_STRING, 8, len("caw\0CAW\0"), "caw\0CAW\0")

        cawc.set_hints(self.connection_c, self.window, self.x, self.y, self.width, self.height);

        conn.core.ChangeProperty(xproto.PropMode.Replace, win, self._NET_WM_DESKTOP, xcb.XA_CARDINAL, 32, 1, struct.pack("I",0xffffffff))

        conn.core.ChangeProperty(xproto.PropMode.Replace, win, self._WIN_STATE, xcb.XA_CARDINAL, 32, 1, struct.pack("I",1))

        conn.core.ChangeProperty(xproto.PropMode.Replace, win, self._NET_WM_WINDOW_TYPE, xcb.XA_ATOM, 32, 1, struct.pack("I",self._NET_WM_WINDOW_TYPE_DOCK))

        conn.core.ChangeWindowAttributes(scr.root,
                xproto.CW.EventMask, 
                [xproto.EventMask.PropertyChange|xproto.EventMask.StructureNotify])

        conn.core.ChangeProperty(xproto.PropMode.Replace, win, self._NET_WM_STATE, xcb.XA_ATOM, 32, 4, struct.pack("IIII",self._NET_WM_STATE_SKIP_TASKBAR, self._NET_WM_STATE_SKIP_PAGER, self._NET_WM_STATE_STICKY, self._NET_WM_STATE_ABOVE))


    def _update_struts(self):
        cawc.update_struts(self.connection_c, self.window,
                self.x, self.y, self.width, self.height)

    def _update_background(self, *_):
        print "updating background"
        conn = self.connection
        rp = self._root_pixmap()
        conn.core.CopyArea(rp,
            self.back_pixmap,
            self._gc,
            self.x, self.y,
            0,0,
            self.width, self.height)

        r = (self.bg_color >> 16) / 255.
        g = ((self.bg_color >> 8) & 0xff) / 255.
        b = (self.bg_color & 0xff) / 255.
        a = self.shading / 255.
        cawc.cairo_set_source_rgba(self._back_cairo_c, r, g, b, a)
        cawc.cairo_rectangle(self._back_cairo_c, 0, 0, self.width, self.height);
        cawc.cairo_fill(self._back_cairo_c)

        i = 0
        r = (self.border_color >> 16) / 255.
        g = ((self.border_color >> 8) & 0xff) / 255.
        b = (self.border_color & 0xff) / 255.
        cawc.cairo_set_source_rgb(self._back_cairo_c, r, g, b)
        while i < self.border_width:
            cawc.cairo_rectangle(self._back_cairo_c, i, i, self.width-2*i, self.height-2*i);
            cawc.cairo_stroke(self._back_cairo_c)
            i+=1

    def _init_widgets(self):
        for w in self.left:
            w.parent = self
            w.setup()

        for w in self.right:
            w.parent = self
            w.setup()

    def mainloop(self):
        self._init_widgets()

        conn = self.connection

        poll = select.poll()
        poll.register(conn.get_file_descriptor(), select.POLLIN)


        self._update_background()
        #self.clear(0, 0, self.width, self.height)
        conn.flush()

        timeout = 0
        while True:
            if self._update:
                self.redraw()
                self._update = False
                conn.flush()

            p = poll.poll(timeout*1000)
            while True:
                try:
                    event = conn.poll_for_event()
                    print "Event:", type(event)
                    print "OpCode:", event.type
                    print "Window:", getattr(event, 'window', None)
                    if event.type == 161:
                        event = xproto.ClientMessageEvent(event)
                    for func in self.events[type(event)]:
                        func(event)
                except xcb.xproto.BadWindow as e:
                    # FIXME: not sure why i have to ignore this
                    # it is a fix for the system tray crashing
                    print "Bad Window:", (e.args[0].bad_value), e.args[0].major_opcode
                except IOError:
                    break


                    #for func in self.events[evt.contents.response_type]:
                        #func(evt)
                    #xcb.free(evt)
                    #evt = xcb.xcb_poll_for_event(self.connection)

            if len(self._timers) > 0:
                now = time.time()
                while self._timers[0][0] <= now:
                    timeout, func = heapq.heappop(self._timers)
                    func()

                timeout = max(self._timers[0][0] - time.time(), 1)
            else:
                timeout = -1

            conn.flush()

    def schedule(self, timeout, func):
        heapq.heappush(self._timers, (timeout + int(time.time()), func))

    def clear(self, x, y, w, h):
        self.connection.core.ClearArea(0, self.window, x, y, w, h)

    def update(self, *args):
        self._update = True

    def redraw(self, *_):
        #print "********** REDRAW **********"
        conn = self.connection
        #if self._background_needs_update:
        #    self._update_background()
        #    self._background_needs_update -= 1
        self.clear(0, 0, self.width, self.height)
        space = self.width-self.border_width*2
        leftx = self.border_width
        y =  (self.height + self._font_height)/2
        for w in self.left:
            wh = w.min_width
            w.x = leftx
            w.width = wh
            cawc.cairo_move_to(self.cairo_c, w.x, y)
            w.draw()
            leftx += w.width
            space -= w.width

        rightx = self.width - self.border_width
        for w in self.right:
            wh = w.min_width
            w.x = rightx - wh
            w.width = wh
            cawc.cairo_move_to(self.cairo_c, w.x, y)
            w.draw()
            rightx -= w.width
            space -= w.width

    def _button_press(self, e):
        print "************ BUTTON NOTIFY ************"
        x = e.event_x
        if x < self.left[-1].x + self.left[-1].width:
            for w in self.left:
                if x >= w.x and x < w.x + w.width:
                    w.buttonpress(e.detail, e.event_x - w.x)
        elif x > self.right[-1].x:
            for w in self.right:
                if x >= w.x and x < w.x + w.width:
                    w.buttonpress(e.detail, e.event_x - w.x)

    def _property_notify(self, e):
        print "************ PROPERTY NOTIFY ************"
        print "Atom:",e.atom
        for func in self.atoms[e.atom]:
            print "Found functions"
            func(e)

    def draw_text(self, text, x=None, color=None):
        if color is None:
            color = self.fg_color

        r = (float(color >> 16)/0xff)
        g = (float(color >> 8 & 0xff)/0xff)
        b = (float(color & 0xff)/0xff)

        cawc.cairo_set_source_rgb(self.cairo_c, r, g, b);

        if x is not None:
            y =  (self.height + self._font_height)/2
            cawc.cairo_move_to(self.cairo_c, x, y)

        cawc.cairo_show_text(self.cairo_c, text);

    def text_width(self, text):
        return cawc.cairo_text_width(self.cairo_c, text)


if __name__ == '__main__':
    caw = Caw(font_face='mintsstrong',
            font_size=10,
            fg_color=0x636363,
            bg_color=0x181818,
            shading=256/4 * 3,
            border_color=0x303030,
            height=10, border_width=1, edge=0)

    caw.left.append(Spacer(3))
    caw.left.append(Desktop(current_fg=0x8fea26))
    caw.left.append(Spacer(5))
    caw.left.append(Systray())
    caw.right.append(Spacer(3))
    caw.right.append(Clock(format='%H:%M:%S', color=0xffffff))
    caw.right.append(Text(" "))
    caw.right.append(Clock(format='%Y.%m.%d', color=0xdddddd))
    caw.right.append(Text(" :: ", 0xcf49eb))
    caw.right.append(Volume(device='PCM'))
    caw.right.append(Text(" ", 0x777777))
    caw.right.append(Volume(percent_color=0xaaaaaa))
    caw.right.append(Text(" :: ", 0xcf49eb))
    caw.right.append(CPU(2, fg_color=0xdddddd))
    caw.right.append(Text(" : ", 0x777777))
    caw.right.append(CPU(1, fg_color=0xdddddd))
    caw.mainloop()
