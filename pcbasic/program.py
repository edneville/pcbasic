"""
PC-BASIC - program.py
Program buffer utilities

(c) 2013, 2014, 2015, 2016 Rob Hagemans
This file is released under the GNU GPL version 3 or later.
"""

import config
import error
import vartypes
import basictoken as tk
import tokenise
import protect
import util
import console
import state
import memory
import logging
# ensure initialisation of state_console_state.sound
import sound


class Program(object):
    """ BASIC program. """

    def __init__(self, max_list_line, allow_protect):
        """ Initialise program. """
        self.erase()
        self.max_list_line = max_list_line
        self.allow_protect = allow_protect

    def erase(self):
        """ Erase the program from memory. """
        state.basic_state.bytecode.truncate(0)
        state.basic_state.bytecode.write('\0\0\0')
        self.protected = False
        self.line_numbers = { 65536: 0 }
        self.last_stored = None
        # reset stacks
        state.basic_state.parser.clear_stacks_and_pointers()

    def truncate(self, rest=''):
        """ Write bytecode and cut the program of beyond the current position. """
        state.basic_state.bytecode.write(rest if rest else '\0\0\0')
        # cut off at current position
        state.basic_state.bytecode.truncate()

    def get_line_number(self, pos):
        """ Get line number for stream position. """
        pre = -1
        for linum in self.line_numbers:
            linum_pos = self.line_numbers[linum]
            if linum_pos <= pos and linum > pre:
                pre = linum
        return pre

    def rebuild_line_dict(self):
        """ Preparse to build line number dictionary. """
        self.line_numbers, offsets = {}, []
        state.basic_state.bytecode.seek(0)
        scanline, scanpos, last = 0, 0, 0
        while True:
            state.basic_state.bytecode.read(1) # pass \x00
            scanline = util.parse_line_number(state.basic_state.bytecode)
            if scanline == -1:
                scanline = 65536
                # if parse_line_number returns -1, it leaves the stream pointer here: 00 _00_ 00 1A
                break
            self.line_numbers[scanline] = scanpos
            last = scanpos
            util.skip_to(state.basic_state.bytecode, tk.end_line)
            scanpos = state.basic_state.bytecode.tell()
            offsets.append(scanpos)
        self.line_numbers[65536] = scanpos
        # rebuild offsets
        state.basic_state.bytecode.seek(0)
        last = 0
        for pos in offsets:
            state.basic_state.bytecode.read(1)
            state.basic_state.bytecode.write(str(vartypes.integer_to_bytes(vartypes.int_to_integer_unsigned((memory.code_start + 1) + pos))))
            state.basic_state.bytecode.read(pos - last - 3)
            last = pos
        # ensure program is properly sealed - last offset must be 00 00. keep, but ignore, anything after.
        state.basic_state.bytecode.write('\0\0\0')

    def update_line_dict(self, pos, afterpos, length, deleteable, beyond):
        """ Update line number dictionary after deleting lines. """
        # subtract length of line we replaced
        length -= afterpos - pos
        addr = (memory.code_start + 1) + afterpos
        state.basic_state.bytecode.seek(afterpos + length + 1)  # pass \x00
        while True:
            next_addr = state.basic_state.bytecode.read(2)
            if len(next_addr) < 2 or next_addr == '\0\0':
                break
            next_addr = vartypes.integer_to_int_unsigned(vartypes.bytes_to_integer(next_addr))
            state.basic_state.bytecode.seek(-2, 1)
            state.basic_state.bytecode.write(str(vartypes.integer_to_bytes(vartypes.int_to_integer_unsigned(next_addr + length))))
            state.basic_state.bytecode.read(next_addr - addr - 2)
            addr = next_addr
        # update line number dict
        for key in deleteable:
            del self.line_numbers[key]
        for key in beyond:
            self.line_numbers[key] += length

    def check_number_start(self, linebuf):
        """ Check if the given line buffer starts with a line number. """
        # get the new line number
        linebuf.seek(1)
        scanline = util.parse_line_number(linebuf)
        c = util.skip_white_read(linebuf)
        # check if linebuf is an empty line after the line number
        empty = (c in tk.end_line)
        # check if we start with a number
        if c in tk.number:
            raise error.RunError(error.STX)
        return empty, scanline

    def store_line(self, linebuf):
        """ Store the given line buffer. """
        if self.protected:
            raise error.RunError(error.IFC)
        # get the new line number
        linebuf.seek(1)
        scanline = util.parse_line_number(linebuf)
        # check if linebuf is an empty line after the line number
        empty = (util.skip_white_read(linebuf) in tk.end_line)
        pos, afterpos, deleteable, beyond = self.find_pos_line_dict(scanline, scanline)
        if empty and not deleteable:
            raise error.RunError(error.UNDEFINED_LINE_NUMBER)
        # read the remainder of the program into a buffer to be pasted back after the write
        state.basic_state.bytecode.seek(afterpos)
        rest = state.basic_state.bytecode.read()
        # insert
        state.basic_state.bytecode.seek(pos)
        # write the line buffer to the program buffer
        length = 0
        if not empty:
            # set offsets
            linebuf.seek(3) # pass \x00\xC0\xDE
            length = len(linebuf.getvalue())
            state.basic_state.bytecode.write('\0' +
                str(vartypes.integer_to_bytes(
                    vartypes.int_to_integer_unsigned(
                        (memory.code_start + 1) + pos + length))) + linebuf.read())
        # write back the remainder of the program
        self.truncate(rest)
        # update all next offsets by shifting them by the length of the added line
        self.update_line_dict(pos, afterpos, length, deleteable, beyond)
        if not empty:
            self.line_numbers[scanline] = pos
        # clear all program stacks
        state.basic_state.parser.clear_stacks_and_pointers()
        self.last_stored = scanline

    def find_pos_line_dict(self, fromline, toline):
        """ Find code positions for line range. """
        deleteable = [ num for num in self.line_numbers if num >= fromline and num <= toline ]
        beyond = [num for num in self.line_numbers if num > toline ]
        # find lowest number strictly above range
        afterpos = self.line_numbers[min(beyond)]
        # find lowest number within range
        try:
            startpos = self.line_numbers[min(deleteable)]
        except ValueError:
            startpos = afterpos
        return startpos, afterpos, deleteable, beyond

    def delete(self, fromline, toline):
        """ Delete range of lines from stored program. """
        fromline = fromline if fromline is not None else min(self.line_numbers)
        toline = toline if toline is not None else 65535
        startpos, afterpos, deleteable, beyond = self.find_pos_line_dict(fromline, toline)
        if not deleteable:
            # no lines selected
            raise error.RunError(error.IFC)
        # do the delete
        state.basic_state.bytecode.seek(afterpos)
        rest = state.basic_state.bytecode.read()
        state.basic_state.bytecode.seek(startpos)
        self.truncate(rest)
        # update line number dict
        self.update_line_dict(startpos, afterpos, 0, deleteable, beyond)
        # clear all program stacks
        state.basic_state.parser.clear_stacks_and_pointers()

    def edit(self, from_line, bytepos=None):
        """ Output program line to console and position cursor. """
        if self.protected:
            console.write(str(from_line)+'\r')
            raise error.RunError(error.IFC)
        # list line
        state.basic_state.bytecode.seek(self.line_numbers[from_line]+1)
        _, output, textpos = tokenise.detokenise_line(state.basic_state.bytecode, bytepos)
        # no newline to avoid scrolling on line 24
        console.list_line(str(output), newline=False)
        # find row, column position for textpos
        newlines, c = 0, 0
        pos_row, pos_col = 0, 0
        if not output:
            return
        for i, byte in enumerate(output):
            c += 1
            if chr(byte) == '\n' or c > state.console_state.screen.mode.width:
                newlines += 1
                c = 0
            if i == textpos:
                pos_row, pos_col = newlines, c
        if textpos > i:
            pos_row, pos_col = newlines, c + 1
        if bytepos:
            console.set_pos(state.console_state.row-newlines+pos_row, pos_col)
        else:
            console.set_pos(state.console_state.row-newlines, 1)

    def renum(self, new_line, start_line, step):
        """ Renumber stored program. """
        new_line = 10 if new_line is None else new_line
        start_line = 0 if start_line is None else start_line
        step = 10 if step is None else step
        # get a sorted list of line numbers
        keys = sorted([ k for k in self.line_numbers.keys() if k >= start_line])
        # assign the new numbers
        old_to_new = {}
        for old_line in keys:
            if old_line < 65535 and new_line > 65529:
                raise error.RunError(error.IFC)
            if old_line == 65536:
                break
            old_to_new[old_line] = new_line
            self.last_stored = new_line
            new_line += step
        # write the new numbers
        for old_line in old_to_new:
            state.basic_state.bytecode.seek(self.line_numbers[old_line])
            # skip the \x00\xC0\xDE & overwrite line number
            state.basic_state.bytecode.read(3)
            state.basic_state.bytecode.write(str(vartypes.integer_to_bytes(vartypes.int_to_integer_unsigned(old_to_new[old_line]))))
        # write the indirect line numbers
        ins = state.basic_state.bytecode
        ins.seek(0)
        while util.skip_to_read(ins, (tk.T_UINT,)) == tk.T_UINT:
            # get the old g number
            jumpnum = vartypes.integer_to_int_unsigned(vartypes.bytes_to_integer(ins.read(2)))
            # handle exception for ERROR GOTO
            if jumpnum == 0:
                pos = ins.tell()
                # skip line number token
                ins.seek(-3, 1)
                if util.backskip_white(ins) == tk.GOTO and util.backskip_white(ins) == tk.ERROR:
                    ins.seek(pos)
                    continue
                ins.seek(pos)
            try:
                newjump = old_to_new[jumpnum]
            except KeyError:
                # not redefined, exists in program?
                if jumpnum not in self.line_numbers:
                    linum = self.get_line_number(ins.tell()-1)
                    console.write_line('Undefined line ' + str(jumpnum) + ' in ' + str(linum))
                newjump = jumpnum
            ins.seek(-2, 1)
            ins.write(str(vartypes.integer_to_bytes(vartypes.int_to_integer_unsigned(newjump))))
        # rebuild the line number dictionary
        new_lines = {}
        for old_line in old_to_new:
            new_lines[old_to_new[old_line]] = self.line_numbers[old_line]
            del self.line_numbers[old_line]
        self.line_numbers.update(new_lines)
        # stop running if we were
        state.basic_state.session.parser.set_pointer(False)
        # reset loop stacks
        state.basic_state.session.parser.clear_stacks()
        # renumber error handler
        if state.basic_state.session.parser.on_error:
            state.basic_state.session.parser.on_error = old_to_new[state.basic_state.session.parser.on_error]
        # renumber event traps
        for handler in state.basic_state.session.parser.events.all:
            if handler.gosub:
                handler.set_jump(old_to_new[handler.gosub])

    def load(self, g, rebuild_dict=True):
        """ Load program from ascii, bytecode or protected stream. """
        self.erase()
        if g.filetype == 'B':
            # bytecode file
            state.basic_state.bytecode.seek(1)
            state.basic_state.bytecode.write(g.read())
        elif g.filetype == 'P':
            # protected file
            state.basic_state.bytecode.seek(1)
            self.protected = self.allow_protect
            protect.unprotect(g, state.basic_state.bytecode)
        elif g.filetype == 'A':
            # assume ASCII file
            # anything but numbers or whitespace: Direct Statement in File
            self.merge(g)
        else:
            logging.debug("Incorrect file type '%s' on LOAD", g.filetype)
        # rebuild line number dict and offsets
        if rebuild_dict and g.filetype != 'A':
            self.rebuild_line_dict()

    def merge(self, g):
        """ Merge program from ascii or utf8 (if utf8_files is True) stream. """
        while True:
            line = g.read_line()
            if line is None:
                break
            linebuf = tokenise.tokenise_line(line)
            if linebuf.read(1) == '\0':
                # line starts with a number, add to program memory; store_line seeks to 1 first
                self.store_line(linebuf)
            else:
                # we have read the :
                if util.skip_white(linebuf) not in tk.end_line:
                    raise error.RunError(error.DIRECT_STATEMENT_IN_FILE)

    def chain(self, action, g, jumpnum, delete_lines):
        """ Chain load the program from g and hand over execution. """
        if delete_lines:
            # delete lines from existing code before merge (without MERGE, this is pointless)
            self.delete(*delete_lines)
        action(g)
        # don't close files!
        # RUN
        state.basic_state.session.parser.jump(jumpnum, err=error.IFC)

    def save(self, g):
        """ Save the program to stream g in (A)scii, (B)ytecode or (P)rotected mode. """
        mode = g.filetype
        if self.protected and mode != 'P':
            raise error.RunError(error.IFC)
        current = state.basic_state.bytecode.tell()
        # skip first \x00 in bytecode
        state.basic_state.bytecode.seek(1)
        if mode == 'B':
            # binary bytecode mode
            g.write(state.basic_state.bytecode.read())
        elif mode == 'P':
            # protected mode
            protect.protect(state.basic_state.bytecode, g)
        else:
            # ascii mode
            while True:
                current_line, output, _ = tokenise.detokenise_line(state.basic_state.bytecode)
                if current_line == -1 or (current_line > self.max_list_line):
                    break
                g.write_line(str(output))
        state.basic_state.bytecode.seek(current)

    def list_lines(self, from_line, to_line):
        """ List line range. """
        if self.protected:
            # don't list protected files
            raise error.RunError(error.IFC)
        # 65529 is max insertable line number for GW-BASIC 3.23.
        # however, 65530-65535 are executed if present in tokenised form.
        # in GW-BASIC, 65530 appears in LIST, 65531 and above are hidden
        if to_line is None:
            to_line = self.max_list_line
        # sort by positions, not line numbers!
        listable = sorted([ self.line_numbers[num]
                                for num in self.line_numbers
                                if num >= from_line and num <= to_line ])
        lines = []
        for pos in listable:
            state.basic_state.bytecode.seek(pos + 1)
            _, line, _ = tokenise.detokenise_line(state.basic_state.bytecode)
            lines.append(str(line))
        # return to direct mode
        state.basic_state.session.parser.set_pointer(False)
        return lines
