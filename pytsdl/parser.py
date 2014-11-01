import enum
import re
import copy
import pypeg2


class StrNameEnum(enum.Enum):
    def __str__(self):
        return self.name


class List:
    def __init__(self, elements):
        self._elements = elements

    def __iter__(self):
        for elem in self._elements:
            yield elem

    def __getitem__(self, i):
        return self._elements[i]


class SimpleValue:
    def __init__(self, value):
        self._value = value

    @property
    def value(self):
        return self._value

    def __str__(self):
        return str(self._value)


class LiteralString(SimpleValue):
    grammar = '"', re.compile(r'(\\.|[^"])*'), '"'

    def __init__(self, string):
        string = bytes(string, 'utf-8').decode('unicode_escape')
        super().__init__(string)


class ConstDecInteger(SimpleValue):
    grammar = re.compile(r'[0-9]+')

    def __init__(self, dec_str):
        super().__init__(int(dec_str))


class ConstOctInteger(SimpleValue):
    grammar = '0', re.compile(r'[0-9]+')

    def __init__(self, oct_str):
        super().__init__(int(oct_str, 8))


class ConstHexInteger(SimpleValue):
    grammar = pypeg2.contiguous(['0x', '0X'], re.compile(r'[0-9a-fA-F]+'))

    def __init__(self, hex_str):
        super().__init__(int(hex_str, 16))


class ConstInteger(SimpleValue):
    grammar = [ConstHexInteger, ConstOctInteger, ConstDecInteger]

    def __init__(self, integer):
        super().__init__(integer.value)


class ConstNumber(SimpleValue):
    grammar = pypeg2.optional(re.compile(r'[+-]')), ConstInteger

    def __init__(self, args):
        mul = 1;

        if len(args) == 2:
            if args[0] == '-':
                mul = -1

            args.pop(0)

        super().__init__(args[0].value * mul)


class Identifier:
    grammar = re.compile(r'^(?!(?:struct|variant|enum|integer|floating_point|string))[A-Za-z_][A-Za-z_0-9]*')

    def __init__(self, name):
        self._name = name

    @property
    def name(self):
        return self._name

    def __str__(self):
        return '<id>{}</id>'.format(self._name)


class PostfixExpr(List):
    def __init__(self, elements):
        super().__init__(elements)

    def __str__(self):
        postfix_expr = '<postfix-expr>'

        for elem in self:
            postfix_expr += str(elem)

        postfix_expr += '</postfix-expr>'

        return postfix_expr


class UnaryExpr:
    def __init__(self, expr):
        if type(expr) is PrimaryExpr:
            self._expr = expr.expr
        else:
            self._expr = expr

    @property
    def expr(self):
        return self._expr

    def __str__(self):
        return str(self._expr)


class PrimaryExpr:
    def __init__(self, expr):
        if type(expr) is ConstNumber or type(expr) is LiteralString:
            self._expr = expr.value
        else:
            self._expr = expr

    @property
    def expr(self):
        return self._expr

    def __str__(self):
        return str(self._expr)


class UnaryExprSubscript:
    grammar = '[', UnaryExpr, ']'

    def __init__(self, expr):
        self._expr = expr.expr

    @property
    def expr(self):
        return self._expr

    def __str__(self):
        return '<subscript-expr>{}</subscript-expr>'.format(str(self._expr))


class AlignAssignment(SimpleValue):
    grammar = 'align', '=', ConstInteger, ';'

    def __init__(self, integer):
        super().__init__(integer.value)


class SizeAssignment(SimpleValue):
    grammar = 'size', '=', ConstInteger, ';'

    def __init__(self, integer):
        super().__init__(integer.value)


class ByteOrder(StrNameEnum):
    NATIVE = 0
    BE = 1
    LE = 2


class ByteOrderAssignment(SimpleValue):
    grammar = 'byte_order', '=', re.compile(r'native|network|be|le'), ';'

    _byteOrderMap = {
        'native': ByteOrder.NATIVE,
        'be': ByteOrder.BE,
        'network': ByteOrder.BE,
        'le': ByteOrder.LE,
    }

    def __init__(self, align):
        super().__init__(ByteOrderAssignment._byteOrderMap[align])


class SignedAssignment(SimpleValue):
    grammar = 'signed', '=', re.compile(r'true|false|1|0'), ';'

    def __init__(self, signed):
        super().__init__(signed in ['true', '1'])


class BaseAssignment(SimpleValue):
    grammar = 'base', '=', [
        ConstInteger,
        re.compile(r'decimal|dec|d|i|u|hexadecimal|hex|x|X|p|octal|oct|o|binary|bin|b')
    ], ';'

    _baseMap = {
        'decimal': 10,
        'dec': 10,
        'd': 10,
        'i': 10,
        'u': 10,
        'hexadecimal': 16,
        'hex': 16,
        'x': 16,
        'X': 16,
        'p': 16,
        'octal': 8,
        'oct': 8,
        'o': 8,
        'binary': 2,
        'bin': 2,
        'b': 2,
    }

    def __init__(self, base):
        if type(base) is ConstInteger:
            value = base.value
        else:
            value = BaseAssignment._baseMap[base]

        super().__init__(value)


class Encoding(StrNameEnum):
    NONE = 0
    UTF8 = 1
    ASCII = 2


class EncodingAssignment(SimpleValue):
    grammar = 'encoding', '=', re.compile(r'none|UTF8|ASCII'), ';'

    _encodingMap = {
        'none': Encoding.NONE,
        'UTF8': Encoding.UTF8,
        'ASCII': Encoding.ASCII,
    }

    def __init__(self, encoding):
        super().__init__(EncodingAssignment._encodingMap[encoding])


class MapAssignment(SimpleValue):
    grammar = 'map', '=', UnaryExpr, ';'

    def __init__(self, expr):
        super().__init__(expr)


class Integer:
    grammar = 'integer', '{', pypeg2.some([
        SignedAssignment,
        ByteOrderAssignment,
        SizeAssignment,
        AlignAssignment,
        BaseAssignment,
        EncodingAssignment,
        MapAssignment,
    ]), '}'

    def __init__(self, assignments):
        self._signed = False
        self._byte_order = ByteOrder.NATIVE
        self._base = 10
        self._encoding = Encoding.NONE
        self._align = None
        self._map = None

        for a in assignments:
            if type(a) is SignedAssignment:
                self._signed = a.value
            elif type(a) is ByteOrderAssignment:
                self._byte_order = a.value
            elif type(a) is SizeAssignment:
                self._size = a.value
            elif type(a) is AlignAssignment:
                self._align = a.value
            elif type(a) is BaseAssignment:
                self._base = a.value
            elif type(a) is EncodingAssignment:
                self._encoding = a.value
            elif type(a) is MapAssignment:
                self._map = a.value

        if self._align is None:
            if self._size % 8 == 0:
                self._align = 8
            else:
                self._align = 1

    @property
    def signed(self):
        return self._signed

    @property
    def byte_order(self):
        return self._byte_order

    @property
    def base(self):
        return self._base

    @property
    def encoding(self):
        return self._encoding

    @property
    def align(self):
        return self._align

    @property
    def size(self):
        return self._size

    @property
    def map(self):
        return self._map

    def __str__(self):
        signed = 'signed="{}"'.format('true' if self._signed else 'false')
        byte_order = 'byte-order="{}"'.format(self._byte_order)
        base = 'base="{}"'.format(self._base)
        encoding = 'encoding="{}"'.format(self._encoding)
        align = 'align="{}"'.format(self._align)
        size = 'size="{}"'.format(self._size)
        integer = '<integer {} {} {} {} {} {}'.format(size, signed, byte_order,
                                                      base, encoding, align)
        map = ''

        if self._map is not None:
            map = '<map>{}</map>'.format(str(self._map))
            integer += '>{}</integer>'.format(map)
        else:
            integer += ' />'

        return integer


class ExpDigAssignment(SimpleValue):
    grammar = 'exp_dig', '=', ConstInteger, ';'

    def __init__(self, exp_dig):
        super().__init__(exp_dig.value)


class MantDigAssignment(SimpleValue):
    grammar = 'mant_dig', '=', ConstInteger, ';'

    def __init__(self, mant_dig):
        super().__init__(mant_dig.value)


class FloatingPoint:
    grammar = 'floating_point', '{', pypeg2.some([
        ExpDigAssignment,
        MantDigAssignment,
        ByteOrderAssignment,
        AlignAssignment,
    ]), '}'

    def __init__(self, assignments):
        self._align = 1
        self._byte_order = ByteOrder.NATIVE

        for a in assignments:
            if type(a) is ExpDigAssignment:
                self._exp_dig = a.value
            elif type(a) is MantDigAssignment:
                self._mant_dig = a.value
            elif type(a) is ByteOrderAssignment:
                self._byte_order = a.value
            elif type(a) is AlignAssignment:
                self._align = a.value

    @property
    def exp_dig(self):
        return self._exp_dig

    @property
    def mant_dig(self):
        return self._mant_dig

    @property
    def byte_order(self):
        return self._byte_order

    @property
    def align(self):
        return self._align

    def __str__(self):
        exp_dig = 'exp-dig="{}"'.format(self._exp_dig)
        mant_dig = 'mant-dig="{}"'.format(self._mant_dig)
        byte_order = 'byte-order="{}"'.format(self._byte_order)
        align = 'align="{}"'.format(self._align)
        float = '<floating_point {} {} {} {} />'.format(exp_dig, mant_dig,
                                                        byte_order, align)

        return float


class String:
    grammar = (
        'string',
        pypeg2.optional((
            '{', EncodingAssignment, '}'
        ))
    )

    def __init__(self, encoding=None):
        self._encoding = Encoding.UTF8

        if encoding is not None:
            self._encoding = encoding.value

    @property
    def encoding(self):
        return self._encoding

    def __str__(self):
        string = '<string encoding="{}" />'.format(self._encoding)

        return string


class Type:
    def __init__(self, t):
        if type(t) is Struct:
            self._type = t.struct
        elif type(t) is Variant:
            self._type = t.variant
        else:
            self._type = t

    @property
    def type(self):
        return self._type

    def __str__(self):
        return str(self._type)


class TypeAlias:
    grammar = 'typealias', Type, ':=', pypeg2.some(Identifier)

    def __init__(self, args):
        self._type = args[0].type
        args.pop(0)
        self._name = []

        for a in args:
            self._name.append(a.name)

    @property
    def type(self):
        return self._type

    @property
    def name(self):
        return ' '.join(self._name)

    def __str__(self):
        type = str(self._type)
        name = 'name="{}"'.format(self.name)

        return '<typealias {}>{}</typealias>'.format(name, type)


class EnumeratorValue:
    grammar = [Identifier, LiteralString], '=', ConstInteger

    def __init__(self, args):
        if type(args[0]) is Identifier:
            self._key = args[0].name
        else:
            self._key = args[0].value

        self._value = args[1].value

    @property
    def key(self):
        return self._key

    @property
    def value(self):
        return self._value


class EnumeratorRange:
    grammar = [Identifier, LiteralString], '=', ConstInteger, '...', ConstInteger

    def __init__(self, args):
        if type(args[0]) is Identifier:
            self._key = args[0].name
        else:
            self._key = args[0].value

        self._low = args[1].value
        self._high = args[2].value

    @property
    def key(self):
        return self._key

    @property
    def low(self):
        return self._low

    @property
    def high(self):
        return self._high


class Enumerator:
    grammar = [
        EnumeratorRange,
        EnumeratorValue,
        Identifier,
        LiteralString,
    ]

    def __init__(self, assignment):
        if type(assignment) is Identifier:
            self._assignment = assignment.name
        elif type(assignment) is LiteralString:
            self._assignment = assignment.value
        else:
            self._assignment = assignment

    @property
    def assignment(self):
        return self._assignment


class Enumerators(List):
    grammar = pypeg2.csl(Enumerator), pypeg2.optional(',')

    def __init__(self, items):
        super().__init__([i.assignment for i in items])


class Enum:
    grammar = (
        'enum',
        pypeg2.optional(Identifier),
        ':',
        Identifier,
        '{',
        Enumerators,
        '}'
    )

    def __init__(self, args):
        self._name = None

        if len(args) == 3:
            self._name = args[0].name
            args.pop(0)

        self._int_type = args[0].name
        self._init_enum_labels(args[1])

    def _init_enum_labels(self, assignment_list):
        self._labels = {}
        cur = 0

        for a in assignment_list:
            if type(a) is str:
                self._labels[a] = (cur, cur)
                cur += 1
            elif type(a) is EnumeratorValue:
                self._labels[a.key] = (a.value, a.value)
                cur = a.value + 1
            elif type(a) is EnumeratorRange:
                self._labels[a.key] = (a.low, a.high)
                cur = a.high + 1

    @property
    def name(self):
        return self._name

    @property
    def int_type(self):
        return self._int_type

    @int_type.setter
    def int_type(self, int_type):
        self._int_type = int_type

    @property
    def labels(self):
        return self._labels

    def __str__(self):
        name = ''

        if self._name is not None:
            name = 'name="{}"'.format(self._name)

        int_type = '<int-type>{}</int-type>'.format(str(self._int_type))
        labels = ''

        for key, value in self._labels.items():
            label_fmt = '<label name="{}" low="{}" high="{}" />'
            label = label_fmt.format(key, value[0], value[1])
            labels += label

        labels = '<labels>{}</labels>'.format(labels)

        return '<enum {}>{}{}</enum>'.format(name, int_type, labels)


class Dot:
    grammar = re.compile(r'\.')

    def __init__(self, args):
        pass

    def __str__(self):
        return '<dot />'


class Arrow:
    grammar = re.compile(r'->')

    def __init__(self, args):
        pass

    def __str__(self):
        return '<arrow />'


PrimaryExpr.grammar = [
    Identifier,
    ConstNumber,
    LiteralString,
    ('(', UnaryExpr, ')'),
]


PostfixExpr.grammar = (
    Identifier,
    pypeg2.maybe_some(
        [
            (Arrow, Identifier),
            (Dot, Identifier),
            UnaryExprSubscript
        ]
    )
)


UnaryExpr.grammar = [
    PostfixExpr,
    PrimaryExpr,
]


class Declarator:
    def __init__(self, name, subscripts):
        self._name = name
        self._subscripts = subscripts

    @property
    def name(self):
        return self._name

    @property
    def subscripts(self):
        return self._subscripts

    def __str__(self):
        name = 'name="{}"'.format(self._name)
        decl = '<declarator {}><subscripts>'.format(name)

        for sub in self._subscripts:
            decl += str(sub)

        decl += '</subscripts></declarator>'

        return decl


class Field:
    grammar = [
        (
            Type,
            Identifier,
            pypeg2.maybe_some(UnaryExprSubscript)
        ),
        (
            pypeg2.some(Identifier),
            pypeg2.maybe_some(UnaryExprSubscript)
        ),
    ]

    def __init__(self, args):
        if type(args[0]) is Type:
            self._type = args[0].type
            args.pop(0)
            decl_name = args[0].name
            args.pop(0)
            self._decl = Declarator(decl_name, args)
        else:
            self._type = []
            subscripts = []

            for a in args:
                if type(a) is Identifier:
                    self._type.append(a.name)
                elif type(a) is UnaryExprSubscript:
                    subscripts.append(a)

            decl_name = self._type.pop()
            self._decl = Declarator(decl_name, subscripts)

    @property
    def type(self):
        if type(self._type) is list:
            return ' '.join(self._type)

        return self._type

    @type.setter
    def type(self, type):
        self._type = type

    @property
    def decl(self):
        return self._decl

    def __str__(self):
        if type(self._type) is list:
            type_in = ' '.join(self._type)
        else:
            type_in = str(self._type)

        t = '<type>{}</type>'.format(type_in)
        decl = str(self._decl)

        return '<field>{}{}</field>'.format(t, decl)


class Entries(List):
    def __init__(self, fields=[]):
        super().__init__(fields)


class StructRef:
    grammar = 'struct', Identifier

    def __init__(self, name):
        self._name = name.name

    @property
    def name(self):
        return self._name

    def __str__(self):
        return '<struct name="{}" />'.format(self._name)


class Scope:
    def _set_entries(self, entries):
        self._entries = entries

    @property
    def entries(self):
        return self._entries

    def _get_entries_str(self):
        s = '<entries>'

        for e in self._entries:
            s += str(e)

        s += '</entries>'

        return s


class StructFull(Scope):
    grammar = (
        'struct',
        pypeg2.optional(Identifier),
        '{', Entries, '}',
        pypeg2.optional(('align', '(', ConstInteger, ')'))
    )

    def __init__(self, args):
        self._name = None
        self._align = None

        if type(args[0]) is Identifier:
            self._name = args[0].name
            args.pop(0)

        self._set_entries(args[0])
        args.pop(0)

        if args:
            self._align = args[0].value

    @property
    def name(self):
        return self._name

    @property
    def align(self):
        return self._align

    def __str__(self):
        name = ''
        align = ''

        if self._name is not None:
            name = 'name="{}"'.format(self._name)

        if self._align is not None:
            align = 'align="{}"'.format(self._align)

        entries = self._get_entries_str()
        struct = '<struct {} {}>{}</struct>'.format(name, align, entries)

        return struct


class Struct:
    grammar = [StructFull, StructRef]

    def __init__(self, struct):
        self._struct = struct

    @property
    def struct(self):
        return self._struct

    def __str__(self):
        return str(self._struct)


class VariantTag:
    grammar = '<', UnaryExpr, '>'

    def __init__(self, expr):
        self._expr = expr

    @property
    def expr(self):
        return self._expr

    def __str__(self):
        return '<tag>{}</tag>'.format(str(self._expr))


class VariantRef:
    grammar = 'variant', Identifier, VariantTag

    def __init__(self, args):
        self._name = args[0].name
        self._tag = args[1].expr

    @property
    def name(self):
        return self._name

    @property
    def tag(self):
        return self._tag

    def __str__(self):
        name = 'name="{}"'.format(self._name)
        variant = '<variant {}>{}</variant>'.format(name, str(self._tag))

        return variant


class VariantFull(Scope):
    grammar = (
        'variant',
        pypeg2.optional(Identifier),
        pypeg2.optional(VariantTag),
        '{', Entries, '}'
    )

    def __init__(self, args):
        self._name = None
        self._tag = None

        if type(args[0]) is Identifier:
            self._name = args[0].name
            args.pop(0)

        if type(args[0]) is VariantTag:
            self._tag = args[0].expr
            args.pop(0)

        self._set_entries(args[0])

    @property
    def name(self):
        return self._name

    @property
    def tag(self):
        return self._tag

    @tag.setter
    def tag(self, tag):
        self._tag = tag

    def __str__(self):
        name = ''
        tag = ''

        if self._name is not None:
            name = 'name="{}"'.format(self._name)

        if self._tag is not None:
            tag = str(self._tag)

        entries = self._get_entries_str()
        fmt = '<variant {}>{}{}</variant>'
        variant = fmt.format(name, tag, entries)

        return variant


class Variant:
    grammar = [VariantFull, VariantRef]

    def __init__(self, variant):
        self._variant = variant

    @property
    def variant(self):
        return self._variant

    def __str__(self):
        return str(self._variant)


class ValueAssignment:
    grammar = Identifier, '=', [Identifier, LiteralString, ConstNumber]

    def __init__(self, args):
        self._key = args[0].name

        if type(args[1]) is LiteralString or type(args[1]) is ConstNumber:
            self._value = args[1].value
        else:
            self._value = args[1]

    @property
    def key(self):
        return self._key

    @property
    def value(self):
        return self._value

    def __str__(self):
        key = 'key="{}"'.format(self._key)
        value = '<value>{}</value>'.format(str(self._value))
        assign = '<value-assignment {}>{}</value-assignment>'.format(key, value)

        return assign


class TypeAssignment:
    grammar = UnaryExpr, ':=', Type

    def __init__(self, args):
        self._key = args[0].expr
        self._type = args[1].type

    @property
    def key(self):
        return self._key

    @property
    def type(self):
        return self._type

    @type.setter
    def type(self, type):
        self._type = type

    def __str__(self):
        key = '<key>{}</key>'.format(self._key)
        type = '<type>{}</type>'.format(str(self._type))
        assign = '<type-assignment>{}{}</type-assignment>'.format(key, type)

        return assign


_common_scope_entries = [
    TypeAlias,
    StructFull,
    VariantFull,
]


_scope_entries = pypeg2.maybe_some((
    [ValueAssignment, TypeAssignment] + _common_scope_entries,
    ';'
))


Entries.grammar = pypeg2.maybe_some((
    [Field] + _common_scope_entries,
    ';'
))


Type.grammar = [Struct, Variant, Enum, Integer, FloatingPoint, String]


class TopLevelScope(Scope):
    @staticmethod
    def _create_scope(clsname, scope_name):
        return type(clsname, (TopLevelScope, object), {
            'grammar': (scope_name, '{', _scope_entries, '}'),
            '_scope_name': scope_name
        })

    def __init__(self, entries=[]):
        self._set_entries(entries)

    def __str__(self):
        s = '<{sn}>{e}</{sn}>'.format(sn=self._scope_name,
                                      e=self._get_entries_str())

        return s


Env = TopLevelScope._create_scope('Env', 'env')
Trace = TopLevelScope._create_scope('Trace', 'trace')
Clock = TopLevelScope._create_scope('Clock', 'clock')
Stream = TopLevelScope._create_scope('Stream', 'stream')
Event = TopLevelScope._create_scope('Event', 'event')
Top = TopLevelScope._create_scope('Top', 'top')


Top.grammar = pypeg2.maybe_some((
    [Env, Trace, Clock, Stream, Event] + _common_scope_entries,
    ';'
))


class ParseError(RuntimeError):
    def __init__(self, str):
        super().__init__(str)


class Parser:
    def get_ast(self, tsdl):
        try:
            ast = pypeg2.parse(tsdl, Top,
                               comment=[pypeg2.comment_c, pypeg2.comment_cpp])
        except (SyntaxError, Exception) as e:
            raise ParseError(str(e))

        return ast

    @staticmethod
    def resolve_type(scope_stores, typeid):
        for scope_store in reversed(scope_stores):
            if typeid in scope_store:
                resolved = scope_store[typeid]

                if type(resolved) is VariantFull:
                    return copy.deepcopy(resolved)

                return scope_store[typeid]

        raise ParseError('cannot resolve type: {}'.format(typeid[1:]))

    @staticmethod
    def resolve_struct(scope_stores, name):
        return Parser.resolve_type(scope_stores, 's' + name)

    @staticmethod
    def resolve_variant(scope_stores, name):
        return Parser.resolve_type(scope_stores, 'v' + name)

    @staticmethod
    def resolve_alias(scope_stores, name):
        return Parser.resolve_type(scope_stores, 'a' + name)

    @staticmethod
    def resolve_types(scope, scope_stores):
        scope_store = {}
        scope_stores.append(scope_store)

        for entry in scope.entries:
            if type(entry) is TypeAlias:
                scope_store['a' + entry.name] = entry.type
            elif type(entry) is StructFull:
                if entry.name is not None:
                    scope_store['s' + entry.name] = entry
            elif type(entry) is VariantFull:
                if entry.name is not None:
                    scope_store['v' + entry.name] = entry
            elif type(entry) is TypeAssignment or type(entry) is Field:
                subtype = entry.type

                if (isinstance(subtype, Scope)):
                    if type(entry) is Field:
                        if type(subtype) is StructFull:
                            if subtype.name is not None:
                                scope_store['s' + subtype.name] = subtype
                        elif type(subtype) is VariantFull:
                            if subtype.name is not None:
                                scope_store['v' + subtype.name] = subtype

                    Parser.resolve_types(subtype, scope_stores)
                else:
                    if type(entry.type) is StructRef:
                        entry.type = Parser.resolve_struct(scope_stores,
                                                           subtype.name)
                    elif type(entry.type) is VariantRef:
                        resolved_variant = Parser.resolve_variant(scope_stores,
                                                                  subtype.name)
                        resolved_variant.tag = subtype.tag
                        entry.type = resolved_variant
                    elif type(entry.type) is str:
                        entry.type = Parser.resolve_alias(scope_stores,
                                                          subtype)
                    elif type(subtype) is Enum:
                        int_type = subtype.int_type
                        subtype.int_type = Parser.resolve_alias(scope_stores,
                                                                int_type)

            if isinstance(entry, Scope):
                Parser.resolve_types(entry, scope_stores)

        scope_stores.pop()

    def parse(self, tsdl):
        ast = self.get_ast(tsdl)
        Parser.resolve_types(ast, [])

        return ast
