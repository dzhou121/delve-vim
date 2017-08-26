# -*- coding: utf-8 -*-
import thread
import threading
import Queue
from multiprocessing.pool import ThreadPool
import os
import neovim
import socket
import json


class DelveAPI(object):

    def __init__(self):
        pass

    def get_vars_params(self, goroutineid):
        return [{
            "Scope": {
                "GoroutineID": goroutineid,
            },
            "Cfg": {
                "FollowPointers": True,
                "MaxVariableRecurse": 2,
                "MaxStringLen": 100,
                "MaxArrayValues": 100,
                "MaxStructFields": 100,
            },
        }]

    def recv_timeout(self, timeout=2):
        total_data = []
        while 1:
            data = self.s.recv(8192)
            if data == '\n':
                break
            elif data:
                total_data.append(data)
                if data.endswith('\n'):
                    break
            else:
                break

        return ''.join(total_data)

    def recv(self, s):
        total_data = []
        while 1:
            data = s.recv(8192)
            if data == '\n':
                break
            elif data:
                total_data.append(data)
                if data.endswith('\n'):
                    break
            else:
                break

        return ''.join(total_data)

    def send(self, msg):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.connect(("10.132.0.2", 2345))
            s.send(json.dumps(msg))
            reply = self.recv(s)
            s.close()
            reply = json.loads(reply)
            return reply
        except Exception as e:
            return {'error': str(e)}

    def list_args(self, goroutineid, queue):
        msg = {
            "method": "RPCServer.ListFunctionArgs",
            "params": self.get_vars_params(goroutineid),
        }
        reply = self.send(msg)
        queue.put(reply)
        return reply

    def get_var(self, goroutineid, var):
        params = self.get_vars_params(goroutineid)
        params[0]["Expr"] = var
        msg = {
            "method": "RPCServer.Eval",
            "params": params,
        }
        return self.send(msg)

    def list_vars(self, goroutineid, queue):
        msg = {
            "method": "RPCServer.ListLocalVars",
            "params": self.get_vars_params(goroutineid),
        }
        reply = self.send(msg)
        queue.put(reply)
        return reply

    def delete_breakpoint(self, bp_id):
        msg = {
            "method": "RPCServer.ClearBreakpoint",
            "params": [{
                "Id": bp_id,
            }]
        }
        return self.send(msg)

    def create_breakpoint(self, fname, line):
        msg = {
            "method": "RPCServer.CreateBreakpoint",
            "params": [{
                "Breakpoint": {
                    "file": fname,
                    "line": line,
                    "goroutine": False,
                    "stacktrace": 0,
                }
            }]
        }
        return self.send(msg)

    def list_breakpoints(self):
        msg = {
            "method": "RPCServer.ListBreakpoints",
            "params": [{
            }]
        }
        return self.send(msg)

    def state(self):
        msg = {
            "method": "RPCServer.State",
            "params": [{}],
        }
        return self.send(msg)

    def command(self, cmd):
        msg = {
            "method": "RPCServer.Command",
            "params": [{
                "name": cmd,
            }],
        }
        return self.send(msg)

    def restart(self):
        msg = {
            "method": "RPCServer.Restart",
            "params": [{
            }],
        }
        return self.send(msg)


@neovim.plugin
class Main(object):
    def __init__(self, vim):
        self.vim = vim
        self.delve = DelveAPI()
        self.prefix = ' '.decode('utf8')
        self.close_prefix = ' '.decode('utf8')
        self.indent = ' ' * 2
        self.local_vars = {}
        self.break_points = {}
        self.current_goroutine = None
        self.delve_buf = None
        self.delve_win = None
        self.delve_file = None
        self.delve_local_dir = None
        self.delve_remote_dir = None
        self.delve_local_sys = None
        self.delve_remote_sys = None
        self.delve_buf_name = '__Delve__'
        self.running = False

    def get_all_signs(self, output):
        signs = []
        lines = output.split("\n")
        for line in lines:
            if "name=delve_breakpoint" in line:
                signs.append(line.split("line=")[1].split(" ")[0])

        return signs

    def start(self):
        pass

    def dump_children(self, buf, child, space):
        for sub_child in child:
            name = sub_child['name']
            value = sub_child['value']
            var_type = sub_child['type']
            if var_type == "string":
                value = '"%s"' % value

            if value:
                var_type = ""
            else:
                var_type = '<%s>' % var_type

            if name or value:
                if (var_type.startswith("<*uint") or
                        var_type.startswith("<*int")):
                    if len(sub_child['children']) == 0:
                        value = "nil "
                elif (var_type.startswith("<*") and
                        (not (len(sub_child['children']) > 0 and
                              len(sub_child['children'][0]['children']) > 0))):
                    value = "nil "

                buf.append("%s%s: %s%s" % (
                    space * " ",
                    name,
                    value,
                    var_type,
                ))

                new_space = space + 4
            else:
                new_space = space
            self.dump_children(buf, sub_child['children'], new_space)

    @neovim.rpc_export('next', sync=False)
    def next(self):
        thread.start_new_thread(self._next, ())

    def _next(self):
        self.async_cmd("sign place 1 line=1 name=delve_next file=%s" %
                       self.delve_file)
        result = self.delve.command("next")
        if result.get('error'):
            return
        self.display_result(result)
        self.async_cmd("sign unplace 1 file=%s" % self.delve_file)

    @neovim.rpc_export('halt', sync=False)
    def halt(self):
        thread.start_new_thread(self._halt, ())

    def _halt(self):
        # self.async_cmd("sign place 1 line=1 name=delve_halt file=%s" %
        #                self.delve_file)
        self.running = False
        result = self.delve.command("halt")
        if result.get('error'):
            self.async_echo(result.get('error'))
            return

        # self.display_result(result)
        # self.async_cmd("sign unplace 1 file=%s" % self.delve_file)
        self.vim.async_call(self.delve_buf_icon, '             ')

    def delve_dir(self):
        if self.delve_local_dir is None:
            self.delve_local_dir = self.vim.eval("g:delve_local_dir")

        if self.delve_remote_dir is None:
            self.delve_remote_dir = self.vim.eval("g:delve_remote_dir")

        if self.delve_local_sys is None:
            self.delve_local_sys = self.vim.eval("g:delve_local_sys")

        if self.delve_remote_sys is None:
            self.delve_remote_sys = self.vim.eval("g:delve_remote_sys")

        return (self.delve_local_dir, self.delve_remote_dir,
                self.delve_local_sys, self.delve_remote_sys)

    def delve_buf_append(self, msg):
        self.delve_buf.append(msg)

    def delve_buf_icon(self, msg):
        self.delve_buf[0] = msg

    def delve_loading_var(self):
        self.delve_buf[2] = '          '

    def step(self):
        result = self.delv_command("step")
        if result.get('error'):
            return

        self.display_result(result)

    @neovim.rpc_export('continue_exec', sync=False)
    def continue_exec(self):
        # self._continue_exec()
        thread.start_new_thread(self._continue_exec, ())

    def _continue_exec(self):
        # self.async_cmd("sign place 1 line=1 name=delve_start file=%s" %
        #                self.delve_file)
        if self.running:
            return

        self.running = True
        self.vim.async_call(self.delve_buf_icon, '             ')
        result = self.delve.command("continue")
        self.running = False
        self.vim.async_call(self.delve_buf_icon, '             ')
        if result.get('error'):
            self.async_echo(result.get('error'))
            return

        self.display_result(result, var=False)
        # self.async_cmd("sign unplace 1 file=%s" % self.delve_file)

    def cursor_goto(self, row, col):
        self.vim.current.window.cursor = (row, col)

    def jump_to(self, local_file, c_line):
        # jump to the local file, this must be executed from non-threaded
        try:
            exists = False
            for win in self.vim.windows:
                if win.buffer.name and \
                        local_file.endswith(win.buffer.name):
                    self.vim.current.window = win
                    self.vim.current.window.cursor = (c_line, 1)
                    self.vim.current.window = self.delve_win
                    exists = True
                    break

            if not exists:
                for win in self.vim.current.tabpage.windows:
                    if not win.buffer.name.endswith(self.delve_buf_name) and \
                            "NERD_tree" not in win.buffer.name:
                        exists = True
                        self.vim.current.window = win
                        self.vim.command("e %s" % local_file)
                        self.vim.current.window.cursor = (c_line, 1)
                        self.vim.current.window = self.delve_win
                        break

                if not exists:
                    self.vim.command("vertical split")
                    self.vim.command("e %s" % local_file)
                    self.vim.current.window.cursor = (c_line, 1)
                    self.vim.current.window = self.delve_win
        except:
            self.vim.command("echo 'failed to jump to %s'" % local_file)

    def display_result(self, result, var=False):
        local_dir, remote_dir, local_sys, remote_sys = self.delve_dir()
        bp_info = result['result']['State']
        current_thread = bp_info.get('currentThread')
        if current_thread is None:
            return

        self.current_goroutine = current_thread["goroutineID"]
        c_line = int(current_thread['line'])
        remote_file = current_thread['file']

        if remote_file.startswith(remote_dir):
            local_file = remote_file.replace(remote_dir, local_dir)
        elif remote_file.startswith(remote_sys):
            local_file = remote_file.replace(remote_sys, local_sys)
        else:
            self.async_echo("cannot jump to remote file %s" % remote_file)
            return

        if not os.path.exists(local_file):
            self.async_echo("cannot jump to file %s" % local_file)
            return

        self.vim.async_call(self.jump_to, local_file, c_line)

        if var:
            self._display_vars()

    @neovim.rpc_export('display_vars', sync=False)
    def display_vars(self):
        thread.start_new_thread(self._display_vars, ())

    def _display_vars(self):
        if self.running:
            return

        if self.current_goroutine is None:
            return

        self.vim.async_call(self.delve_loading_var)
        vars_queue = Queue.Queue()
        vars_thread = threading.Thread(
            target=self.delve.list_vars,
            args=(self.current_goroutine, vars_queue))
        args_queue = Queue.Queue()
        args_thread = threading.Thread(
            target=self.delve.list_args,
            args=(self.current_goroutine, args_queue))
        args_thread.start()
        vars_thread.start()

        r = args_queue.get()
        source_local_vars = r['result']['Args']

        r = vars_queue.get()
        source_local_vars = source_local_vars + r['result']['Variables']

        args_thread.join()
        vars_thread.join()

        local_vars = {}
        self.format_parent({}, local_vars, self.local_vars,
                           source_local_vars)
        self.local_vars = local_vars
        self.set_local_vars()

    def short_var(self, var):
        i = len(var) - 1
        while i >= 0:
            if var[i] == '*' or var[i] == ']' or var[i] == '<'\
                    or var[i] == ' ':
                break
            i -= 1
        prefix = var[0:i+1]
        var = '%s%s' % (prefix,
                        var[i+1:].split('/')[-1])
        return var

    def format_var_line(self, var):
        name = var['name']
        # if ' ' in name:
        #     name = name.split(' ')[-1]
        value = var['value']
        var_type = var['type']
        var_realtype = var.get('realtype', '')
        if var_realtype:
            var_realtype = '.(%s)' % self.short_var(var_realtype)

        var_type = '<%s%s>' % (self.short_var(var_type), var_realtype)
        if value:
            if var_type == "<string>":
                value = value.replace("\n", "\\n")
                value = '"%s"' % value
                var_type = ""
            elif var_type in ["<bool>", "<uint>", "<uint32>",
                              "<int>", "<int64>", "int32"]:
                var_type = ""
            else:
                value = value + ' '

        if var_type.startswith('<*') and not var['children']:
            value = "nil "

        prefix = len(self.prefix) * ' '
        if var['children']:
            if var.get('expanded'):
                prefix = self.close_prefix
            else:
                prefix = self.prefix
        return("%s%s: %s%s" % (prefix, name, value, var_type))

    def buf_set_lines(self, lines):
        cursor = self.vim.current.window.cursor
        self.delve_buf[2:] = lines
        self.vim.current.window.cursor = cursor

    def get_current_cursor(self):
        self.cursor = self.vim.current.window.cursor

    def set_current_cursor(self):
        if self.cursor:
            self.vim.current.window.cursor = self.cursor

    def set_local_vars(self, expand_all=None):
        lines = self.local_vars_lines(expand_all=expand_all)
        self.vim.async_call(self.buf_set_lines, lines)

    def local_vars_lines(self, expand_all=None):
        local_vars = [var for name, var in self.local_vars.items()]
        local_vars.sort(key=lambda d: len(d['children']) == 0)
        lines = []
        indent_num = 0
        for var in local_vars:
            if expand_all is not None:
                var['expanded'] = expand_all
            lines.append((self.indent * indent_num +
                          self.format_var_line(var)).encode('utf8'))
            self._openfold_lines(lines, indent_num, var, expand_all=expand_all)
        return lines

    def format_parent(self, parent, children, original_children,
                      source_children):
        previous_value = ""
        for i, child in enumerate(source_children):
            name = child['name']
            if parent.get('type', '').startswith('map['):
                if i % 2 == 0:
                    name = '[%s] key' % str(i / 2)
                else:
                    name = '[%s] value' % str(i / 2)
            elif parent.get('type', '').startswith('[]'):
                name = '[' + str(i) + ']'

            value = child['value']
            var_type = child['type']
            # prefix = ''
            # if var_type.startswith('*'):
            #     prefix = '*'
            # if var_type.startswith('chan '):
            #     prefix = 'chan '
            # if var_type.startswith('chan *'):
            #     prefix = 'chan *'
            # var_type = '%s%s' % (prefix,
            #                      child['type'].split('/')[-1])
            if parent.get('interface') and child['name'] == 'data':
                self.format_parent(parent,
                                   children,
                                   original_children,
                                   child['children'])
                parent['realtype'] = var_type
            elif name:
                children[name] = {}
                parent_var = parent.get('var', '')
                if parent_var:
                    parent_var += "."
                    if parent.get('realtype'):
                        realtype = parent['realtype']
                        parent_var = '%s(%s).' % (parent_var,
                                                  self.short_var(realtype))
                child_var = child['name'].split('.')[-1]
                children[name]['var'] = (
                    "%s%s" % (parent_var, child_var))
                if parent.get('type', '').startswith('map['):
                    if i % 2 != 0:
                        children[name]['var'] = (
                            '%s["%s"]' % (parent.get('var', ''),
                                          previous_value)
                        )
                elif parent.get('type', '').startswith('[]'):
                    children[name]['var'] = (
                        '%s[%s]' % (parent.get('var', ''),
                                    i)
                    )

                # self.async_echo(name)
                previous_value = child['value']
                children[name]['name'] = name
                children[name]['value'] = value
                children[name]['type'] = var_type
                children[name]['children'] = {}
                children[name]['interface'] = child.get('kind') == 20
                children[name]['expanded'] = original_children.get(
                    name, {}).get('expanded', False)
                self.format_parent(
                    children[name],
                    children[name]['children'],
                    original_children.get(name, {}).get('children', {}),
                    child['children'])
            else:
                if value:
                    name = "noname"
                    children[name] = {}
                    children[name]['name'] = name
                    children[name]['value'] = value
                    children[name]['type'] = var_type
                    children[name]['children'] = {}
                    children[name]['interface'] = child.get('kind') == 20
                    self.format_parent(
                        children[name],
                        children[name]['children'],
                        original_children.get(
                            name, {}).get('children', {}),
                        child['children'])
                else:
                    self.format_parent(parent,
                                       children,
                                       original_children,
                                       child['children'])

    @neovim.rpc_export('restart', sync=False)
    def restart(self):
        thread.start_new_thread(self._restart, ())

    def _restart(self):
        self.async_cmd("sign place 1 line=1 name=delve_restart file=%s" %
                       self.delve_file)
        self.vim.async_call(self.delve_buf_append,
                            "start sending restart")
        reply = self.delve.restart()
        self.vim.async_call(self.delve_buf_append,
                            json.dumps(reply))
        self.async_cmd("sign unplace 1 file=%s" % self.delve_file)

    def get_key(self, line, indent_num):
        parts = line.split(self.indent)
        return parts[indent_num][2:].split(':')[0]

    def find_parent_key(self, keys, buf, indent_num, n):
        line = buf[n].decode('utf8')
        key = self.get_key(line, indent_num)
        keys.insert(0, key)
        if indent_num == 0:
            return

        parent_prefix = (indent_num - 1) * self.indent + self.close_prefix
        while 1:
            n = n - 1
            line = buf[n].decode('utf8')
            if line.startswith(parent_prefix):
                self.find_parent_key(keys, buf, indent_num - 1, n)
                return

    @neovim.rpc_export('open_all_fold', sync=False)
    def open_all_fold(self):
        for buf in self.vim.buffers:
            if buf.name.endswith(self.delve_buf_name):
                self.set_local_vars(expand_all=True)

    @neovim.rpc_export('close_all_fold', sync=False)
    def close_all_fold(self):
        for buf in self.vim.buffers:
            if buf.name.endswith(self.delve_buf_name):
                self.set_local_vars(expand_all=False)

    @neovim.rpc_export('openfold', sync=False)
    def openfold(self):
        exits = False
        for win in self.vim.windows:
            if win.buffer.name.endswith(self.delve_buf_name):
                buf = win.buffer
                n = win.cursor[0] - 1
                exits = True
                break

        if not exits:
            return

        line = buf[n].decode('utf8')
        indent_num = 0
        parts = line.split(self.indent)
        for p in parts:
            if p == '':
                indent_num += 1
            else:
                if p.startswith(self.prefix):
                    self._openfold(buf, indent_num, n)
                    return
                elif p.startswith(self.close_prefix):
                    self._closefold(buf, indent_num, n)
                    return

    def _closefold(self, buf, indent_num, n):
        parent = self.find_parent(buf, indent_num, n)
        parent['expanded'] = False
        for i, line in enumerate(buf):
            if i < n + 1:
                continue
            line = line.decode('utf8')
            j = len(self.indent * indent_num) + len(self.prefix)
            c = line[j:j + 2]
            if c != '  ' and c != self.prefix and c != self.close_prefix:
                break

        del buf[n+1:i]
        buf[n] = buf[n].decode('utf8').replace(
            self.close_prefix, self.prefix).encode('utf8')

    def find_parent(self, buf, indent_num, n):
        keys = []
        self.find_parent_key(keys, buf, indent_num, n)

        children = self.local_vars
        for k in keys:
            parent = children[k]
            children = parent['children']

        return parent

    def _openfold_lines(self, lines, indent_num, parent, expand_all=None):
        children = parent['children']
        children = [child for i, child in children.items()]

        if parent.get('type', '').startswith('map['):
            children.sort(key=lambda d: d['name'])
        else:
            children.sort(key=lambda d: len(d['children']) == 0)
        indent_num += 1
        if expand_all is False:
            for child in children:
                child['expanded'] = expand_all
                self._openfold_lines(lines, indent_num, child,
                                     expand_all=expand_all)
        if parent.get('expanded', False):
            for child in children:
                if expand_all is not None:
                    child['expanded'] = expand_all
                lines.append((self.indent * indent_num +
                             self.format_var_line(child)).encode('utf8'))
                self._openfold_lines(lines, indent_num, child,
                                     expand_all=expand_all)

    def get_var(self, parent):
        parent['downloaded'] = True
        result = self.delve.get_var(self.current_goroutine, parent['var'])
        if result.get('error'):
            return

        source_vars = result['result']['Variable']
        local_vars = {}
        try:
            self.format_parent(parent, local_vars,
                               parent.get('children', {}),
                               source_vars["children"])
        except Exception as e:
            self.vim.async_call(self.delve_buf_append, str(e))
            return
        parent['children'] = local_vars
        self.set_local_vars()

    def _openfold(self, buf, indent_num, n):
        parent = self.find_parent(buf, indent_num, n)
        parent['expanded'] = True
        if not parent.get('downloaded', False):
            if self.current_goroutine is not None:
                thread.start_new_thread(self.get_var, (parent,))
        buf[n] = buf[n].decode('utf8').replace(
            self.prefix, self.close_prefix).encode('utf8')

        lines = []
        self._openfold_lines(lines, indent_num, parent)
        buf.append(lines, n + 1)

    def find_delve_win(self):
        for w in self.vim.current.tabpage.windows:
            if self.delve_buf_name in w.buffer.name:
                self.delve_win = w
                return w
        self.delve_win = None

    def find_delve_buf(self):
        for buf in self.vim.buffers:
            if self.delve_buf_name in buf.name:
                self.delve_buf = buf
                return buf

    def init_delve_buf(self):
        self.find_delve_buf()
        pwd = self.vim.command_output("silent pwd")[1:]
        self.delve_file = os.path.join(pwd, self.delve_buf_name)
        self.delve_dir()
        self.init_breakpoints()
        self.halt()
        self.vim.command("setlocal filetype=delve")
        self.vim.command("setlocal buftype=nofile")
        self.vim.command("setlocal bufhidden=hide")
        self.vim.command("setlocal noswapfile")
        self.vim.command("setlocal nobuflisted")
        self.vim.command("setlocal nomodifiable")
        self.vim.command("setlocal nolist")
        self.vim.command("setlocal nowrap")

        self.vim.command("nmap cgc c")
        self.vim.command("nunmap cgc")
        self.vim.command("nmap dd d")
        self.vim.command("nunmap dd")

        maps = [
            ['s',             'delve#start()'],
            ['c',             'delve#continue()'],
            ['r',             'delve#restart()'],
            ['p',             'delve#halt()'],
            ['m',             'delve#next()'],
            ['o',             'delve#openfold()'],
            ['O',             'delve#open_all_fold()'],
            ['X',             'delve#close_all_fold()'],
            ['d',             'delve#display_vars()'],
        ]

        for keymap in maps:
            cmd = 'nnoremap <silent> <buffer> %s :call %s<CR>' % (
                keymap[0], keymap[1]
            )

            self.vim.command(cmd)

    @neovim.rpc_export('open_window', sync=False)
    def open_window(self):
        self._open_window()

    def _open_window(self):
        self.find_delve_win()
        if self.delve_win:
            if self.vim.current.tabpage == self.delve_win.tabpage:
                old_win = self.vim.current.window
                old_is_self = self.delve_buf_name in old_win.buffer.name
                self.vim.current.window = self.delve_win
                self.delve_win = None
                self.vim.command("close")
                if not old_is_self:
                    self.vim.current.window = old_win
                return
            else:
                self.vim.current.window = self.delve_win
                return

        # check if the buf exists or not
        delve_buf_exits = self.delve_buf is not None

        # at this step, it means the win is not open, so open it first
        self.vim.command(
            "keepalt vertical botright split %s" % self.delve_buf_name)
        self.find_delve_win()

        if not delve_buf_exits:
            self.init_delve_buf()
            lines = [
                '             ',
                '                 ',
                '                 ',
            ]

            self.vim.command("setlocal modifiable")
            self.delve_buf[:] = lines

    @neovim.function("_delve", sync=True)
    def testcommand(self, args):
        self.vim.vars['delve#channel_id'] = self.vim.channel_id

    def init_breakpoints(self):
        thread.start_new_thread(self._init_breakpoints, ())

    def _init_breakpoints(self):
        result = self.delve.list_breakpoints()
        if result.get('error'):
            return

        breakpoints = result['result'].get('Breakpoints', [])
        for bp in breakpoints:
            path = bp['file'].replace(self.delve_remote_dir,
                                      self.delve_local_dir)
            row = bp["line"]
            bp_key = "%s:%s" % (path, row)
            self.break_points[bp_key] = bp['id']

    @neovim.rpc_export('new_breakpoint', sync=False)
    def new_breakpoint(self):
        path = self.vim.command_output("silent echo expand('%:p')")[1:]
        row = self.vim.current.window.cursor[0]

        if not path:
            return

        local_dir = self.vim.eval("g:delve_local_dir")
        if local_dir not in path:
            return

        remote_dir = self.vim.eval("g:delve_remote_dir")
        remote_path = path.replace(local_dir, remote_dir)

        signs = self.vim.command_output("silent sign place file=%s" % path)
        bp_key = "%s:%s" % (path, row)

        if str(row) in signs:
            # self._delete_breakpoint(bp_key, row, path)
            thread.start_new_thread(self._delete_breakpoint,
                                    (bp_key, row, path))
        else:
            # self._create_breakpoint(bp_key, row, path, remote_path)
            thread.start_new_thread(self._create_breakpoint,
                                    (bp_key, row, path, remote_path))

    def async_echo(self, text):
        self.async_cmd("echo '%s'" % text)

    def async_echoerr(self, text):
        self.async_cmd("echoerr '%s'" % text)

    def async_cmd(self, cmd):
        # use vim async call to call vim command, for use from thread
        self.vim.async_call(self.vim.command, cmd)

    def _delete_breakpoint(self, bp_key, row, path):
        bp_id = self.break_points.get(bp_key)
        if bp_id:
            reply = self.delve.delete_breakpoint(bp_id)
            error = reply.get('error', '')
            if error:
                self.async_cmd('echo "%s"' % error)

            self.async_cmd("sign unplace %s file=%s" % (row, path))

    def _create_breakpoint(self, bp_key, row, path, remote_path):
        cmd = "sign place %s line=%s name=delve_breakpoint file=%s" % (
            row, row, path
        )
        self.async_cmd(cmd)
        reply = self.delve.create_breakpoint(remote_path, row)
        error = reply.get('error', '')
        if not error:
            bp_id = reply['result']['Breakpoint']['id']
            self.break_points[bp_key] = bp_id
        if not error or error.startswith("Breakpoint exists"):
            cmd = ("sign place %s line=%s "
                   "name=delve_breakpoint_confirmed file=%s" % (
                       row, row, path
                   ))
            self.async_cmd(cmd)
        else:
            self.async_cmd("sign unplace %s file=%s" % (row, path))
            self.async_cmd('echo "%s"' % error)

if __name__ == "__main__":
    d = DelveAPI()
    print d.print_var(7, "request")
