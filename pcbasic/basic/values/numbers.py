"""
PC-BASIC - numbers.py
Integer and Floating Point values

(c) 2013, 2014, 2015, 2016 Rob Hagemans
This file is released under the GNU GPL version 3.
"""

# descriptions of the Microsoft Binary Format found here:
# http://www.experts-exchange.com/Programming/Languages/Pascal/Delphi/Q_20245266.html
# http://www.boyet.com/Articles/MBFSinglePrecision.html
#
# single precision:                      m3 | m2 | m1 | exponent
# double precision:  m7 | m6 | m5 | m4 | m3 | m2 | m1 | exponent
# where:
#     m1 is most significant byte => sbbb|bbbb
#     m7 is the least significant byte
#     m = mantissa byte
#     s = sign bit
#     b = bit
#
# The exponent is biased by 128.
# There is an assumed 1 bit after the radix point (so the assumed mantissa is 0.1ffff... where f's are the fraction bits)

import struct
import math

from .. import tokens as tk
from .. import error


# for to_str
# for numbers, tab and LF are whitespace
BLANKS = b' \t\n'
# ASCII separators - these cause string representations to evaluate to zero
SEPARATORS = b'\x1c\x1d\x1f'



##############################################################################
# value base class

class Value(object):
    """Abstract base class for value types."""

    sigil = None
    size = None

    def __init__(self, buffer, values):
        """Initialise the value."""
        if buffer is None:
            buffer = memoryview(bytearray(self.size))
        self._buffer = memoryview(buffer)
        self._values = values

    def __str__(self):
        """String representation for debugging."""
        try:
            return b'%s[%s %s]' % (self.sigil, bytes(self.to_bytes()).encode('hex'), repr(self.to_value()))
        except Exception:
            return b'%s[%s <detached>]' % (self.sigil, bytes(self.to_bytes()).encode('hex'))

    __repr__ = __str__

    def to_value(self):
        """Convert to Python value."""

    def clone(self):
        """Create a copy."""
        return self.__class__(None, self._values).from_bytes(self._buffer)

    def new(self):
        """Create a new null value."""
        return self.__class__(None, self._values)

    def copy_from(self, other):
        """Copy another value into this one."""
        self._buffer[:] = other._buffer
        return self

    def to_bytes(self):
        """Get a copy of the byte representation."""
        return bytearray(self._buffer)

    def from_bytes(self, in_bytes):
        """Copy a new byte representation into the value."""
        self._buffer[:] = in_bytes
        return self

    def view(self):
        """Get a reference to the storage space."""
        return self._buffer


##############################################################################
# numeric value base class

class Number(Value):
    """Abstract base class for numeric value."""

    zero = None
    pos_max = None
    neg_max = None

    def __init__(self, buffer, values):
        """Initialise the number."""
        Value.__init__(self, buffer, values)
        self.error_handler = values.error_handler

    def to_double(self):
        """Convert to double."""

    def to_single(self):
        """Convert to single."""

    def to_float(self, allow_double=True):
        """Convert to float."""

    def add(self, rhs):
        """Add another Number."""
        return self.clone().iadd(rhs)

    def iadd(self, rhs):
        """Add another Number, in-place."""


##############################################################################
# integer number

class Integer(Number):
    """16-bit signed little-endian integer."""

    sigil = b'%'
    size = 2

    pos_max = b'\xff\x7f'
    neg_max = b'\xff\xff'

    def is_zero(self):
        """Value is zero."""
        return self._buffer == b'\0\0'

    def is_negative(self):
        """Value is negative."""
        return (ord(self._buffer[-1]) & 0x80) != 0

    def sign(self):
        """Sign of value."""
        return -1 if (ord(self._buffer[-1]) & 0x80) != 0 else (0 if self._buffer == b'\0\0' else 1)

    def to_int(self, unsigned=False):
        """Return value as Python int."""
        if unsigned:
            return struct.unpack('<H', self._buffer)[0]
        else:
            return struct.unpack('<h', self._buffer)[0]

    def from_int(self, in_int, unsigned=False):
        """Set value to Python int."""
        if unsigned:
            # we can in fact assign negatives as 'unsigned'
            if in_int < 0:
                in_int += 0x10000
            intformat = '<H'
            maxint = 0xffff
        else:
            intformat = '<h'
            maxint = 0x7fff
        if not (-0x8000 <= in_int <= maxint):
            raise error.RunError(error.OVERFLOW)
        struct.pack_into(intformat, self._buffer, 0, in_int)
        return self

    def to_integer(self, unsigned=False):
        """Convert to Integer (no-op)."""
        return self

    def to_double(self):
        """Convert to double."""
        return Double(None, self._values).from_integer(self)

    def to_single(self):
        """Convert to single."""
        return Single(None, self._values).from_integer(self)

    def to_float(self, allow_double=True):
        """Convert to float."""
        return Single(None, self._values).from_integer(self)

    to_value = to_int
    from_value = from_int

    def to_token(self):
        """Return signed value as integer token."""
        if self._buffer[1] == b'\0':
            byte = ord(self._buffer[0])
            # although there is a one-byte token for '10', we don't write it.
            if byte < 10:
                return chr(ord(tk.C_0) + byte)
            else:
                return tk.T_BYTE + self._buffer[0]
        else:
            return tk.T_INT + self._buffer.tobytes()

    def to_token_linenum(self):
        """Return unsigned value as line number token."""
        return tk.T_UINT + self._buffer.tobytes()

    def to_token_hex(self):
        """Return unsigned value as hex token."""
        return tk.T_HEX + self._buffer.tobytes()

    def to_token_oct(self):
        """Return unsigned value as oct token."""
        return tk.T_OCT + self._buffer.tobytes()

    def from_token(self, token):
        """Set value to signed or unsigned integer token."""
        d = bytes(token)[0]
        if d in (tk.T_OCT, tk.T_HEX, tk.T_INT, tk.T_UINT):
            self._buffer[:] = token[-2:]
        elif d == tk.T_BYTE:
            self._buffer[:] = token[-1] + b'\0'
        elif tk.C_0 <= d <= tk.C_10:
            self._buffer[:] = chr(ord(d) - 0x11) + b'\0'
        else:
            raise ValueError('%s is not an Integer token.' % repr(token))
        return self

    # representations

    def to_oct(self):
        """Convert integer to str in octal representation."""
        if self.is_zero():
            return b'0'
        return oct(self.to_int(unsigned=True))[1:]

    def to_hex(self):
        """Convert integer to str in hex representation."""
        return hex(self.to_int(unsigned=True))[2:].upper()

    def to_str(self, leading_space, type_sign):
        """Convert integer to str in decimal representation."""
        intstr = bytes(self.to_int())
        if leading_space and intstr[0] != b'-':
            return b' ' + intstr
        else:
            return intstr

    def from_oct(self, oct_repr):
        """Convert str in octal representation to integer."""
        # oct representations may be interrupted by blanks
        val = int(oct_repr.strip(BLANKS), 8) if oct_repr else 0
        return self.from_int(val, unsigned=True)

    def from_hex(self, hex_repr):
        """Convert str in hexadecimal representation to integer."""
        # hex representations must be contiguous
        val = int(hex_repr, 16) if hex_repr else 0
        return self.from_int(val, unsigned=True)

    def from_str(self, dec_repr):
        """Convert str in decimal representation to integer."""
        return self.from_int(int(dec_repr.strip(BLANKS)))

    # operations

    def iround(self):
        """Round in-place (no-op)."""

    def itrunc(self):
        """Truncate towards zero in-place (no-op)."""

    def ifloor(self):
        """Truncate towards negative infinity in-place (no-op)."""

    def ineg(self):
        """Negate in-place."""
        if self._buffer == '\x00\x80':
            raise error.RunError(error.OVERFLOW)
        lsb = (ord(self._buffer[0]) ^ 0xff) + 1
        msb = ord(self._buffer[1]) ^ 0xff
        # apply carry
        if lsb > 0xff:
            lsb -= 0x100
            msb += 1
        # ignore overflow, since -0 == 0
        self._buffer[:] = chr(lsb) + chr(msb & 0xff)
        return self

    def iabs(self):
        """Absolute value in-place."""
        if (ord(self._buffer[-1]) & 0x80):
            return self.ineg()

    def iadd(self, rhs):
        """Add another Integer in-place."""
        lsb = ord(self._buffer[0]) + ord(rhs._buffer[0])
        msb = ord(self._buffer[1]) + ord(rhs._buffer[1])
        # apply carry
        if lsb > 0xff:
            lsb -= 0x100
            msb += 1
        # overflow if signs were equal and have changed
        if (ord(self._buffer[1]) > 0x7f) == (ord(rhs._buffer[1]) > 0x7f) != (msb > 0x7f):
            raise error.RunError(error.OVERFLOW)
        self._buffer[:] = chr(lsb) + chr(msb & 0xff)
        return self

    def isub(self, rhs):
        """Subtract another Integer in-place."""
        # we can't apply the neg on the lhs and avoid a copy
        # because of things like -32768 - (-1)
        return self.iadd(rhs.clone().ineg())

    # no imul - we always promote to float first for multiplication
    # no idiv - we always promote to float first for true division

    def idiv_int(self, rhs):
        """Perform integer division."""
        if rhs.is_zero():
            # division by zero - return single-precision maximum
            if self.is_negative():
                max_val = Single(None, self._values).from_bytes(Single.neg_max)
            else:
                max_val = Single(None, self._values).from_bytes(Single.pos_max)
            raise ZeroDivisionError(max_val)
        dividend = self.to_int()
        divisor = rhs.to_int()
        # BASIC intdiv rounds to zero, Python's floordiv to -inf
        if (dividend >= 0) == (divisor >= 0):
            return self.from_int(dividend // divisor)
        else:
            return self.from_int(-(abs(dividend) // abs(divisor)))

    def imod(self, rhs):
        """Left modulo right."""
        if rhs.is_zero():
            # division by zero - return single-precision maximum
            if self.is_negative():
                max_val = Single(None, self._values).from_bytes(Single.neg_max)
            else:
                max_val = Single(None, self._values).from_bytes(Single.pos_max)
            raise ZeroDivisionError(max_val)
        dividend = self.to_int()
        divisor = rhs.to_int()
        # BASIC MOD has same sign as dividend, Python mod has same sign as divisor
        mod = dividend % divisor
        if dividend < 0 or mod < 0:
            mod -= divisor
        return self.from_int(mod)

    # relations

    def gt(self, rhs):
        """Greater than."""
        if isinstance(rhs, Float):
            # upgrade to Float
            return rhs.new().from_integer(self).gt(rhs)
        isneg = ord(self._buffer[-1]) & 0x80
        if isneg != (ord(rhs._buffer[-1]) & 0x80):
            return not(isneg)
        # compute the unsigned (not absolute!) >
        lmsb = ord(self._buffer[1]) & 0x7f
        rmsb = ord(rhs._buffer[1]) & 0x7f
        if lmsb > rmsb:
            return True
        elif lmsb < rmsb:
            return False
        return ord(self._buffer[0]) > ord(rhs._buffer[0])

    def eq(self, rhs):
        """Equals."""
        if isinstance(rhs, Float):
            # upgrade to Float
            return rhs.new().from_integer(self).eq(rhs)
        return self._buffer == rhs._buffer


##############################################################################
# floating-point base class

class Float(Number):
    """Abstract base class for floating-point value."""

    digits = None
    pos_max = None
    neg_max = None

    exp_sign = None

    # properties

    def is_zero(self):
        """Value is zero."""
        return self._buffer[-1] == b'\0'

    def is_negative(self):
        """Value is negative."""
        return self._buffer[-2] >= b'\x80'

    def sign(self):
        """Sign of value."""
        return 0 if self._buffer[-1] == b'\0' else (-1 if (ord(self._buffer[-2]) & 0x80) != 0 else 1)

    # BASIC type conversions

    def from_integer(self, in_integer):
        """Convert Integer to Float."""
        return self.from_int(in_integer.to_int())

    def to_integer(self, unsigned=False):
        """Convert Float to Integer."""
        return Integer(None, self._values).from_int(self.to_int(), unsigned)

    # Python float conversions

    def to_value(self):
        """Return value as Python float."""
        exp = ord(self._buffer[-1]) - self._bias
        if exp == -self._bias:
            return 0.
        # unpack as unsigned long int
        man = struct.unpack(self._intformat, bytearray(self._buffer[:-1]) + b'\0')[0]
        # prepend assumed bit and apply sign
        if man & self._signmask:
            man = -man
        else:
            man |= self._signmask
        return man * 2.**exp

    def from_value(self, in_float):
        """Set to value of Python float."""
        if in_float == 0.:
            self._buffer[:] = b'\0' * self.size
            return self
        neg = in_float < 0
        exp = int(math.log(abs(in_float), 2) - self._shift)
        man = int(abs(in_float) * 0.5**exp)
        exp += self._bias
        # why do we need this here?
        man, exp = self._bring_to_range(man, exp, self._posmask, self._mask)
        if not self._check_limits(exp, neg):
            return self
        struct.pack_into(self._intformat, self._buffer, 0, man & (self._mask if neg else self._posmask))
        self._buffer[-1] = chr(exp)
        return self


    # Python int conversions

    def to_int(self):
        """Return value rounded to Python int."""
        man, neg = self._to_int_den()
        # carry: round to nearest, halves away from zero
        if man & 0x80:
            man += 0x80
        # note that -man >> 8 and -(man >> 8) are different
        # due to Python's rounding rules
        return -(man >> 8) if neg else man >> 8

    def from_int(self, in_int):
        """Set value to Python int."""
        if in_int == 0:
            self._buffer[:] = b'\0' * self.size
        else:
            neg = in_int < 0
            man, exp = self._bring_to_range(abs(in_int), self._bias, self._posmask, self._mask)
            if not self._check_limits(exp, neg):
                return self
            struct.pack_into(self._intformat, self._buffer, 0, man & (self._mask if neg else self._posmask))
            self._buffer[-1] = chr(exp)
        return self

    def to_int_truncate(self):
        """Truncate float to integer."""
        man, neg = self._to_int_den()
        # discard carry
        return -(man >> 8) if neg else man >> 8

    def mantissa(self):
        """Integer value of mantissa."""
        exp, man, neg = self._denormalise()
        return -(man >> 8) if neg else (man >> 8)

    # in-place unary operations

    def ineg(self):
        """Negate in-place."""
        self._buffer[-2] = chr(ord(self._buffer[-2]) ^ 0x80)
        return self

    def iabs(self):
        """Absolute value in-place."""
        self._buffer[-2] = chr(ord(self._buffer[-2]) & 0x7F)
        return self

    def iround(self):
        """Round in-place."""
        return self.from_int(self.to_int())

    def itrunc(self):
        """Truncate towards zero in-place."""
        return self.from_int(self.to_int_truncate())

    def ifloor(self):
        """Truncate towards negative infinity in-place."""
        if self.is_negative():
            self.itrunc().isub(self.new().from_bytes(self._one))
        else:
            self.itrunc()
        return self

    # relations

    def gt(self, rhs):
        """Greater than."""
        if isinstance(rhs, Integer):
            # upgrade rhs to Float
            return self.gt(self.new().from_integer(rhs))
        elif isinstance(rhs, Double) and isinstance(self, Single):
            # upgrade to Double
            return Double(None, self._values).from_single(self).gt(rhs)
        rhsneg = rhs.is_negative()
        # treat zero separately to avoid comparing different mantissas
        # zero is only greater than negative
        if self.is_zero():
            return bool(rhsneg) and not rhs.is_zero()
        isneg = self.is_negative()
        if isneg != rhsneg:
            return not(isneg)
        if isneg:
            return rhs._abs_gt(self)
        return self._abs_gt(rhs)

    def eq(self, rhs):
        """Equals."""
        if isinstance(rhs, Integer):
            # upgrade rhs to Float
            return self.eq(self.new().from_integer(rhs))
        elif isinstance(rhs, Double) and isinstance(self, Single):
            # upgrade to Double
            return Double(None, self._values).from_single(self).eq(rhs)
        # all zeroes are equal
        if self.is_zero():
            return rhs.is_zero()
        return self._buffer == rhs._buffer

    # in-place binary operations

    def iadd(self, right):
        """Add in-place."""
        return self._normalise(*self._add_den(self._denormalise(), right._denormalise()))

    def isub(self, right):
        """Subtract in-place."""
        rexp, rman, rneg = right._denormalise()
        return self._normalise(*self._add_den(self._denormalise(), (rexp, rman, not rneg)))

    def imul(self, right_in):
        """Multiply in-place."""
        global lden_s, rden_s, sden_s
        if self.is_zero() or right_in.is_zero():
            # set any zeroes to standard zero
            self._buffer[:] = b'\0' * self.size
            return self
        lexp, lman, lneg = self._denormalise()
        rexp, rman, rneg = right_in._denormalise()
        lden_s, rden_s = lman, rman
        lexp += rexp - right_in._bias - 8
        lneg = (lneg != rneg)
        lman *= rman
        sden_s = lman
        if lexp < -31:
            self._buffer[:] = b'\0' * self.size
            return self._buffer
        # drop some precision
        lman, lexp = self._bring_to_range(lman, lexp, self._den_mask>>4, self._den_upper>>4)
        # rounding quirk
        if lman & 0xf == 0x9:
            lman &= (self._carrymask + 0xfe)
        self._normalise(lexp, lman, lneg)
        return self

    def idiv(self, right_in):
        """Divide in-place."""
        if right_in.is_zero():
            # division by zero - return max float with the type and sign of self
            self.from_bytes(self.neg_max if self.is_negative() else self.pos_max)
            raise ZeroDivisionError(self)
        if self.is_zero():
            return self
        lexp, lman, lneg = self._div_den(self._denormalise(), right_in._denormalise())
        # normalise and return
        return self._normalise(lexp, lman, lneg)

    def ipow_int(self, expt):
        """Raise to integer power in-place."""
        return self._ipow_int(expt.to_int())


    # decimal representations

    def to_str(self, leading_space, type_sign):
        """Convert to string representation."""
        if self.is_zero():
            return (' ' * leading_space) + '0' + (self.sigil * type_sign)
        # sign or leading space
        sign = ''
        if self.is_negative():
            sign = '-'
        elif leading_space:
            sign = ' '
        num, exp10 = self.to_decimal()
        ndigits = self.digits
        digitstr = get_digits(num, ndigits, remove_trailing=True)
        # exponent for scientific notation
        exp10 += ndigits - 1
        if exp10 > ndigits - 1 or len(digitstr)-exp10 > ndigits + 1:
            # use scientific notation
            valstr = scientific_notation(digitstr, exp10, self.exp_sign, digits_to_dot=1, force_dot=False)
        else:
            # use decimal notation
            type_sign = '' if not type_sign else self.sigil
            valstr = decimal_notation(digitstr, exp10, type_sign, force_dot=False)
        return sign + valstr

    def to_decimal(self, digits=None):
        """Return value as mantissa and decimal exponent."""
        if digits is None:
            # we'd be better off storing these (and self._ten) in denormalised form
            lim_bot = self.new().from_bytes(self._lim_bot)
            lim_top = self.new().from_bytes(self._lim_top)
            digits = self.digits
        elif digits > 0:
            lim_bot = self.new().from_int(10**(digits-1))._just_under()
            lim_top = self.new().from_int(10**digits)._just_under()
        else:
            return 0, 0
        tden = lim_top._denormalise()
        bden = lim_bot._denormalise()
        exp10 = 0
        den = self._denormalise()
        while self._abs_gt_den(den, tden):
            den = self._div10_den(den)
            exp10 += 1
        # rounding - gets us close to GW results
        den = self._apply_carry_den(den)
        while self._abs_gt_den(bden, den):
            den = self._mul10_den(den)
            exp10 -= 1
        # rounding - gets us close to GW results
        den = self._apply_carry_den(den)
        # round to int
        exp, man, neg = den
        exp -= self._bias
        if exp > 0:
            man <<= exp
        else:
            man >>= -exp
        # here we don't care about overflowing the mantissa as we output it as int
        if man & 0x80:
            man += 0x80
        num = -(man >> 8) if neg else man >> 8
        return num, exp10

    def from_decimal(self, mantissa, exp10):
        """Set value to mantissa and decimal exponent."""
        den = self.from_int(mantissa)._denormalise()
        # apply decimal exponent
        while (exp10 < 0):
            den = self._div10_den(den)
            exp10 += 1
        while (exp10 > 0):
            den = self._mul10_den(den)
            exp10 -= 1
        return self._normalise(*den)

    ##########################################################################
    # implementation: decimal representations only

    _one = None
    _ten = None
    _lim_bot = None
    _lim_top = None

    def _apply_carry_den(self, den):
        """Round the carry byte (to be used only in to_decimal)."""
        exp, man, neg = den
        # apply_carry()
        # carry bit set? then round up
        if (man & 0xff) > 0x7f:
            man += 0x100
        # overflow?
        if man >= self._den_upper:
            exp += 1
            man >>= 1
        # discard carry
        man ^= man & 0xff
        return exp, man, neg

    def _just_under(self):
        """Return the largest floating-point number less than the given value."""
        lexp, lman, lneg = self._denormalise()
        # decrease mantissa by one
        return self.new()._normalise(lexp, lman - 0x100, lneg)

    def _abs_gt_den(self, lden, rden):
        """Absolute value is greater than."""
        lexp, lman, _ = lden
        rexp, rman, _ = rden
        if lexp != rexp:
            return (lexp > rexp)
        return (lman > rman)

    def _div10_den(self, lden):
        """Divide by 10 in-place."""
        exp, man, neg = self._div_den(lden,
            self.new().from_bytes(self._ten)._denormalise())
        # perhaps this should be in _div_den
        while man < self._den_mask:
            exp -= 1
            man <<= 1
        return exp, man, neg

    def _mul10_den(self, den):
        """Multiply in-place by 10."""
        exp, man, neg = den
        # 10x == 2(x+4x)
        return self._add_den((exp+1, man, neg), (exp+3, man, neg))


    ##########################################################################
    # implementation: general

    _bias = None
    _shift = None
    _intformat = None
    _mask = None
    _posmask = None
    _signmask = None
    _den_mask = None
    _den_upper = None
    _carrymask = None

    def _denormalise(self):
        """Denormalise to shifted mantissa, exp, sign."""
        exp = ord(self._buffer[-1])
        man = struct.unpack(self._intformat, b'\0' + bytearray(self._buffer[:-1]))[0] | self._den_mask
        neg = self.is_negative()
        return exp, man, neg

    def _normalise(self, exp, man, neg):
        """Normalise from shifted mantissa, exp, sign."""
        global pden_s
        # zero denormalised mantissa -> make zero
        if man == 0 or exp <= 0:
            self._buffer[:] = b'\0' * self.size
            return self
        # shift left if subnormal
        while man < (self._den_mask-1):
            exp -= 1
            man <<= 1
        pden_s = man
        # round to nearest; halves to even (Gaussian rounding)
        round_up = (man & 0xff > 0x80) or (man & 0xff == 0x80 and man & 0x100 == 0x100)
        man = (man & self._carrymask) + 0x100 * round_up
        if man >= self._den_upper:
            exp += 1
            man >>= 1
        # pack into byte representation
        struct.pack_into(self._intformat, self._buffer, 0, (man>>8) & (self._mask if neg else self._posmask))
        if self._check_limits(exp, neg):
            self._buffer[-1] = chr(exp)
        return self

    def _to_int_den(self):
        """Denormalised float to integer."""
        exp, man, neg = self._denormalise()
        exp -= self._bias
        if exp > 0:
            man <<= exp
        else:
            man >>= -exp
        return man, neg

    def _check_limits(self, exp, neg):
        """Overflow and underflow check
        returns:
            True if nonzero non-infinite
            False if underflow
        raises:
            OverflowError if overflow
        """
        if exp > 255:
            self.from_bytes(self.neg_max if neg else self.pos_max)
            raise OverflowError(self)
        elif exp <= 0:
            # set to zero, but leave mantissa as is
            self._buffer[-1:] = chr(0)
            return False
        return True

    def _bring_to_range(self, man, exp, lower, upper):
        """Bring mantissa to range (posmask, mask]."""
        while abs(man) <= lower:
            exp -= 1
            man <<= 1
        while abs(man) > upper:
            exp += 1
            man >>= 1
        return man, exp

    def _abs_gt(self, rhs):
        """Absolute values greater than."""
        # don't compare zeroes
        if self.is_zero():
            return False
        rhscopy = bytearray(rhs._buffer)
        # so long as the sign is the same ...
        rhscopy[-2] &= (ord(self._buffer[-2]) | 0x7f)
        # ... we can compare floats as if they were ints
        for l, r in reversed(zip(self._buffer, rhscopy)):
            # memoryview elements are str, bytearray elements are int
            if ord(l) > r:
                return True
            elif ord(l) < r:
                return False
        # equal
        return False

    def _add_den(self, lden, rden):
        """Denormalised add."""
        lexp, lman, lneg = lden
        rexp, rman, rneg = rden
        global lden_s, rden_s, sden_s
        if rexp == 0:
            return lexp, lman, lneg
        if lexp == 0:
            return rexp, rman, rneg
        # ensure right is larger
        if lexp > rexp or (lexp == rexp and lman > rman):
            lexp, lman, lneg, rexp, rman, rneg = rexp, rman, rneg, lexp, lman, lneg
        # zero flag for quirky rounding
        # only set if all the bits we lose by matching exponents were zero
        zero_flag = lman & ((1<<(rexp-lexp))-1) == 0
        sub_flag = lneg != rneg
        # match exponents
        lman >>= (rexp - lexp)
        lexp = rexp
        lden_s = lman
        rden_s = rman
        # shortcut (this affects quirky rounding)
        if (lman < 0x80 or lman == 0x80 and zero_flag) and sub_flag:
            return rexp, rman, rneg
        # add mantissas, taking sign into account
        if not sub_flag:
            man, neg = lman + rman, lneg
            if man >= self._den_upper:
                lexp += 1
                man >>= 1
        else:
            man, neg = rman - lman, rneg
        # break tie for rounding if we're at exact half after dropping digits
        if not zero_flag and not sub_flag:
            man |= 0x1
        # attempt to match GW-BASIC subtraction rounding
        sden_s = -man if sub_flag else man
        if sub_flag and (man & 0x1c0 == 0x80) and (man & 0x1df != 0x80):
            man &= (self._carrymask + 0x7f)
        return lexp, man, neg

    def _ipow_int(self, expt):
        """Raise to int power in-place."""
        # exponentiation by squares
        if expt < 0:
            self._ipow_int(-expt)
            self = self.new().from_bytes(self._one).idiv(self)
        elif expt > 1:
            if (expt % 2) == 0:
                self._ipow_int(expt // 2)
                self.imul(self)
            else:
                base = self.clone()
                self._ipow_int((expt-1) // 2)
                self.imul(self)
                self.imul(base)
        elif expt == 0:
            self = self.from_bytes(self._one)
        return self

    def _div_den(self, lden, rden):
        """Denormalised divide."""
        lexp, lman, lneg = lden
        rexp, rman, rneg = rden
        # signs
        lneg = (lneg != rneg)
        # subtract exponentials
        lexp -= rexp - self._bias - 8
        # long division of mantissas
        work_man = lman
        lman = 0
        lexp += 1
        while (rman > 0):
            lman <<= 1
            lexp -= 1
            if work_man > rman:
                work_man -= rman
                lman += 1
            rman >>= 1
        return lexp, lman, lneg



##############################################################################
# single-precision floating-point number

class Single(Float):
    """Single-precision MBF float."""

    sigil = b'!'
    size = 4

    exp_sign = b'E'
    digits = 7

    pos_max = b'\xff\xff\x7f\xff'
    neg_max = b'\xff\xff\xff\xff'

    _intformat = '<L'

    _bias = 128 + 24
    _shift = _bias - 129

    _den_mask = 0x80000000
    _den_upper = _den_mask * 2
    _carrymask = 0xffffff00

    _signmask = 0x800000
    _mask = 0xffffff
    _posmask = 0x7fffff

    _one = b'\x00\x00\x00\x81'
    _ten = b'\x00\x00\x20\x84'
    _lim_top = b'\x7f\x96\x18\x98' # 9999999, highest float less than 10e+7
    _lim_bot = b'\xff\x23\x74\x94' # 999999.9, highest float  less than 10e+6

    def to_token(self):
        """Return value as Single token."""
        return tk.T_SINGLE + self._buffer.tobytes()

    def from_token(self, token):
        """Set value to Single token."""
        if bytes(token)[0] != tk.T_SINGLE:
            raise ValueError('%s is not a Single token.' % repr(token))
        self._buffer[:] = token[-4:]
        return self

    def to_single(self):
        """Convert single to single (no-op)."""
        return self

    def to_double(self):
        """Convert single to double."""
        return Double(None, self._values).from_single(self)

    def to_float(self, allow_double=True):
        """Convert single to float."""
        return self


###############################################################################
# double-precision floating-point number

class Double(Float):
    """Double-precision MBF float."""

    sigil = b'#'
    size = 8

    exp_sign = b'D'
    digits = 16

    pos_max = b'\xff\xff\xff\xff\xff\xff\x7f\xff'
    neg_max = b'\xff\xff\xff\xff\xff\xff\xff\xff'

    _intformat = '<Q'

    _bias = 128 + 56
    _shift = _bias - 129

    _den_mask = 0x8000000000000000
    _den_upper = _den_mask * 2
    _carrymask = 0xffffffffffffff00

    _signmask = 0x80000000000000
    _mask = 0xffffffffffffff
    _posmask = 0x7fffffffffffff

    _one = b'\x00\x00\x00\x00\x00\x00\x00\x81'
    _ten = b'\x00\x00\x00\x00\x00\x00\x20\x84'
    _lim_top = b'\xff\xff\x03\xbf\xc9\x1b\x0e\xb6' # highest float less than 10e+16
    _lim_bot = b'\xff\xff\x9f\x31\xa9\x5f\x63\xb2' # highest float less than 10e+15

    def from_single(self, in_single):
        """Convert Single to Double in-place."""
        self._buffer[:4] = b'\0\0\0\0'
        self._buffer[4:] = in_single._buffer
        return self

    def to_token(self):
        """Return value as Single token."""
        return tk.T_DOUBLE + self._buffer.tobytes()

    def from_token(self, token):
        """Set value to Single token."""
        if bytes(token)[0] != tk.T_DOUBLE:
            raise ValueError('%s is not a Double token.' % repr(token))
        self._buffer[:] = token[-8:]
        return self

    def to_single(self):
        """Round double to single."""
        mybytes = self.to_bytes()
        single = Single(None, self._values).from_bytes(mybytes[4:])
        exp, man, neg = single._denormalise()
        # carry byte
        man += mybytes[3]
        return single._normalise(exp, man, neg)

    def to_double(self):
        """Convert double to double (no-op)."""
        return self

    def to_float(self, allow_double=True):
        """Convert double to float."""
        if allow_double:
            return self
        return self.to_single()


##############################################################################
# convert string representation to float

def str_to_decimal(s, allow_nonnum=True):
    """Return Float value for Python string."""
    found_sign, found_point, found_exp = False, False, False
    found_exp_sign, exp_neg, neg = False, False, False
    exp10, exponent, mantissa, digits, zeros = 0, 0, 0, 0, 0
    is_double, is_single = False, False
    for c in s:
        # ignore whitespace throughout (x = 1   234  56  .5  means x=123456.5 in gw!)
        if c in BLANKS:
            continue
        if c in SEPARATORS:
            # ASCII separator chars invariably lead to zero result
            return False, 0, 0
        # determine sign
        if (not found_sign):
            found_sign = True
            # number has started; if no sign encountered here, sign must be pos.
            if c in b'+-':
                neg = (c == b'-')
                continue
        # parse numbers and decimal points, until 'E' or 'D' is found
        if (not found_exp):
            if b'0' <= c <= b'9':
                mantissa *= 10
                mantissa += ord(c) - ord(b'0')
                if found_point:
                    exp10 -= 1
                # keep track of precision digits
                if mantissa != 0:
                    digits += 1
                    if found_point and c == b'0':
                        zeros += 1
                    else:
                        zeros = 0
                continue
            elif c == '.':
                found_point = True
                continue
            elif c.upper() in b'DE':
                found_exp = True
                is_double = (c.upper() == b'D')
                continue
            elif c == b'!':
                # makes it a single, even if more than eight digits specified
                is_single = True
                break
            elif c == b'#':
                is_double = True
                break
            else:
                if allow_nonnum:
                    break
                raise ValueError('Non-numerical character in string')
        # parse exponent
        elif (not found_exp_sign):
            # exponent has started; if no sign given, it must be pos.
            found_exp_sign = True
            if c in b'+-':
                exp_neg = (c == b'-')
                continue
        if (b'0' <= c <= b'9'):
            exponent *= 10
            exponent += ord(c) - ord(b'0')
            continue
        else:
            if allow_nonnum:
                break
            raise ValueError('Non-numerical character in string')
    if exp_neg:
        exp10 -= exponent
    else:
        exp10 += exponent
    # eight or more digits means double, unless single override
    if digits - zeros > 7 and not is_single:
        is_double = True
    return is_double, -mantissa if neg else mantissa, exp10


##############################################################################
# convert decimal to string representation

#FIXME: this can be replaced with str and zfill
def get_digits(num, digits, remove_trailing):
    """Get the digits for an int."""
    digitstr = str(abs(num))
    digitstr = '0'*(digits-len(digitstr)) + digitstr[:digits]
    if remove_trailing:
        return digitstr.rstrip('0')
    return digitstr

def scientific_notation(digitstr, exp10, exp_sign, digits_to_dot, force_dot):
    """Put digits in scientific E-notation."""
    valstr = digitstr[:digits_to_dot]
    if len(digitstr) > digits_to_dot:
        valstr += '.' + digitstr[digits_to_dot:]
    elif len(digitstr) == digits_to_dot and force_dot:
        valstr += '.'
    exponent = exp10 - digits_to_dot + 1
    valstr += exp_sign
    if exponent < 0:
        valstr += '-'
    else:
        valstr += '+'
    valstr += get_digits(abs(exponent), digits=2, remove_trailing=False)
    return valstr

def decimal_notation(digitstr, exp10, type_sign, force_dot):
    """Put digits in decimal notation."""
    # digits to decimal point
    exp10 += 1
    if exp10 >= len(digitstr):
        valstr = digitstr + '0'*(exp10-len(digitstr))
        if force_dot:
            valstr += '.'
        if not force_dot or type_sign == '#':
            valstr += type_sign
    elif exp10 > 0:
        valstr = digitstr[:exp10] + '.' + digitstr[exp10:]
        if type_sign == '#':
            valstr += type_sign
    else:
        if force_dot:
            valstr = '0'
        else:
            valstr = ''
        valstr += '.' + '0'*(-exp10) + digitstr
        if type_sign == '#':
            valstr += type_sign
    return valstr


lden_s, rden_s, sden_s, pden_s = 0,0,0,0
