#!/usr/bin/env python
#
# Copyright (c) 2014 Krzysztof Jusiak (krzysztof at jusiak dot net)
#
# Distributed under the Boost Software License, Version 1.0.
# (See accompanying file LICENSE_1_0.txt or copy at http://www.boost.org/LICENSE_1_0.txt)
#
import os
import sys
from optparse import OptionParser
from clang.cindex import Index
from clang.cindex import TranslationUnit
from clang.cindex import Cursor
from clang.cindex import CursorKind
from clang.cindex import Config
from clang.cindex import ExceptionSpecificationKind

if sys.version_info < (3, 0):
    import __builtin__
    def str(object, unused = None):
        return __builtin__.str(object)

    def bytes(object, unused = None):
        return __builtin__.bytes(object)

class mock_method:
    operators = {
        'operator,'   : 'comma_operator',
        'operator!'   : 'logical_not_operator',
        'operator!='  : 'inequality_operator',
        'operator%'   : 'modulus_operator',
        'operator%='  : 'modulus_assignment_operator',
        'operator&'   : 'address_of_or_bitwise_and_operator',
        'operator&&'  : 'logical_and_operator',
        'operator&='  : 'bitwise_and_assignment_operator',
        'operator()'  : 'function_call_or_cast_operator',
        'operator*'   : 'multiplication_or_dereference_operator',
        'operator*='  : 'multiplication_assignment_operator',
        'operator+'   : 'addition_or_unary_plus_operator',
        'operator++'  : 'increment1_operator',
        'operator+='  : 'addition_assignment_operator',
        'operator-'   : 'subtraction_or_unary_negation_operator',
        'operator--'  : 'decrement1_operator',
        'operator-='  : 'subtraction_assignment_operator',
        'operator->'  : 'member_selection_operator',
        'operator->*' : 'pointer_to_member_selection_operator',
        'operator/'   : 'division_operator',
        'operator/='  : 'division_assignment_operator',
        'operator<'   : 'less_than_operator',
        'operator<<'  : 'left_shift_operator',
        'operator<<=' : 'left_shift_assignment_operator',
        'operator<='  : 'less_than_or_equal_to_operator',
        'operator='   : 'assignment_operator',
        'operator=='  : 'equality_operator',
        'operator>'   : 'greater_than_operator',
        'operator>='  : 'greater_than_or_equal_to_operator',
        'operator>>'  : 'right_shift_operator',
        'operator>>=' : 'right_shift_assignment_operator',
        'operator[]'  : 'array_subscript_operator',
        'operator^'   : 'exclusive_or_operator',
        'operator^='  : 'exclusive_or_assignment_operator',
        'operator|'   : 'bitwise_inclusive_or_operator',
        'operator|='  : 'bitwise_inclusive_or_assignment_operator',
        'operator||'  : 'logical_or_operator',
        'operator~'   : 'complement_operator'
    }

    def __init__(self, result_type, name, is_const, is_template, args, args_types, exception_specification_kind): #_size, args, args_prefix = 'arg'):
        self.result_type = result_type
        self.name = name
        self.is_const = is_const
        self.is_template = is_template
        self.args = args
        self.args_types = args_types
        self.exception_specification_kind = exception_specification_kind

    def __named_args(self):
        result = []
        for i in range(len(self.args)):
            i and result.append(', ')
            result.append(self.args_prefix + str(i))
        return ''.join(result)

    def __named_args_with_types(self):
        if (self.args == ''):
            return ''
        result = []
        in_type = False
        i = 0
        for c in self.args:
            if c in ['<', '(']:
                in_type = True
            elif c in ['>', ')']:
                in_type = False
            if not in_type and c == ',':
                result.append(' ' + self.args_prefix + str(i))
                i+=1
            result.append(c)
        result.append(' ' + self.args_prefix + str(i))
        return ''.join(result)

    def to_string(self, gap = '    '):
        mock = []
        name = self.name
        if self.name in self.operators:
            mock.append(gap)
            mock.append(
                "virtual %(result_type)s %(name)s(%(args)s) %(const)s{ %(return)s %(body)s; }\n" % {
                    'result_type' : self.result_type,
                    'name' : self.name,
                    'args' : self.__named_args_with_types(),
                    'const' : self.is_const and 'const ' or '',
                    'return' : self.result_type.strip() != 'void' and 'return' or '',
                    'body' : self.operators[self.name] + "(" + self.__named_args() + ")"
                }
            )
            name = self.operators[self.name]

        mock.append(gap)        
        
        s = self.args_types[1:-1]
        args = []
        counter = 0
        arg = ''
        for symbol in s:
            if counter == 0 and symbol == ',':
                args.append(arg.strip())
                arg = ''
                continue
            elif '<' == symbol:
                counter += 1
            elif '>' == symbol:
                counter -= 1
            arg += symbol
            
        args.append(arg.strip())
        args = ', '.join([f'({arg})' for arg in args])
        
        attrs = ['override']
        if self.is_const:
            attrs.append('const')

        if ExceptionSpecificationKind.BASIC_NOEXCEPT == self.exception_specification_kind:
            attrs.append('noexcept')

        attrs = ', '.join(attrs)    

        mock.append(
            f'MOCK_METHOD(({self.result_type}), {name}, {args}), ({attrs}));'
        )

        return ''.join(mock)

class mock_generator:
    def __is_template_class(self, expr):
        return '<' in expr

    def __get_result_type(self, tokens, name):
        result_type = []
        for token in tokens:
            if token in [name, 'operator']:
                break
            if token not in ['virtual', 'inline', 'volatile']:
                result_type.append(token)
            if token in ['const', 'volatile']:
                result_type.append(' ')
        return ''.join(result_type)

    def __pretty_template(self, expr):
        first = False
        typename = []
        typenames = []
        for token in expr.split("::")[-1]:
            if token == '<':
                first = True
            elif token == ',':
                typenames.append(''.join(typename))
                typename = []
            elif token == '>':
                typenames.append(''.join(typename))
                typename = []
            elif token == ' ':
                continue
            elif first:
                typename.append(token)

        result = []
        if len(typenames) > 0:
            result.append("template<")
            for i, t in enumerate(typenames):
                i != 0 and result.append(", ")
                result.append("typename ")
                result.append(t)
            result.append(">")
            result.append("\n")

        return ''.join(result)

    def __pretty_mock_methods(self, mock_methods):
        result = []
        for i, mock_method in enumerate(mock_methods):
            i and result.append('\n')
            result.append(mock_method.to_string())
            first = False
        return ''.join(result)

    def __pretty_namespaces_begin(self, expr):
        result = []
        for i, namespace in enumerate(expr.split("::")[0 : -1]):
            i and result.append('\n')
            result.append("namespace " + namespace + " {")
        return ''.join(result)

    def __pretty_namespaces_end(self, expr):
        result = []
        for i, namespace in enumerate(expr.split("::")[0 : -1]):
            i and result.append('\n')
            result.append("} // namespace " + namespace)
        return ''.join(result)

    def __get_interface(self, expr):
        result = []
        ignore = False
        for token in expr.split("::")[-1]:
            if token == '<':
                ignore = True
            if not ignore:
                result.append(token)
            if token == '>':
                ignore = False
        return ''.join(result)

    def __get_mock_methods(self, node, mock_methods, expr = ""):
        name = node.displayname
        if node.kind == CursorKind.CXX_METHOD:
            spelling = node.spelling
            tokens = [token.spelling for token in node.get_tokens()]
            file = node.location.file.name
            if node.is_pure_virtual_method():
                mock_methods.setdefault(expr, [file]).append(
                    mock_method(
                         self.__get_result_type(tokens, spelling),
                         spelling,
                         node.is_const_method(),
                         self.__is_template_class(expr),
                         node.get_arguments(),
                         name,
                         node.exception_specification_kind,
                    )
                )
        elif node.kind in [CursorKind.CLASS_TEMPLATE, CursorKind.STRUCT_DECL, CursorKind.CLASS_DECL, CursorKind.NAMESPACE]:
            expr = expr == "" and name or expr + (name == "" and "" or "::") + name
            if expr.startswith(self.expr):
                [self.__get_mock_methods(c, mock_methods, expr) for c in node.get_children()]
        else:
            [self.__get_mock_methods(c, mock_methods, expr) for c in node.get_children()]

    def __generate_file(self, expr, mock_methods, file_type, file_template_type):
        interface = self.__get_interface(expr)
        mock_file = {
            'hpp' : self.mock_file_hpp % { 'interface' : interface },
            'cpp' : self.mock_file_cpp % { 'interface' : interface },
        }
        path = self.path + "/" + mock_file[file_type]
        not os.path.exists(os.path.dirname(path)) and os.makedirs(os.path.dirname(path))
        namespaces = f'{expr[:expr.rfind("::")]}::'
        with open(path, 'w') as file:
            file.write(file_template_type % {
                'mock_file_hpp' : mock_file['hpp'],
                'mock_file_cpp' : mock_file['cpp'],
                'generated_dir' : self.path,
                'guard' : mock_file[file_type].replace('.', '_').upper(),
                'dir' : os.path.dirname(mock_methods[0]),
                'file' : os.path.basename(mock_methods[0]),
                'namespaces' : namespaces,
                'interface' : interface,
                'template_interface' : expr.split("::")[-1],
                'template' : self.__pretty_template(expr),
                'mock_methods' : self.__pretty_mock_methods(mock_methods[1:])
            })

    def __parse(self, files, args):
        tmp_file = b"~.hpp"
        def generate_includes(includes):
            result = []
            for include in includes:
                result.append("#include \"%(include)s\"\n" % { 'include' : include })
            return ''.join(result)

        return Index.create(excludeDecls = True).parse(
            path = tmp_file
          , args = args
          , unsaved_files = [(tmp_file, bytes(generate_includes(files), "utf-8"))]
          , options = TranslationUnit.PARSE_SKIP_FUNCTION_BODIES | TranslationUnit.PARSE_INCOMPLETE
        )

    def __init__(self, files, args, expr, path, mock_file_hpp, file_template_hpp, mock_file_cpp, file_template_cpp):
        self.expr = expr
        self.path = path
        self.mock_file_hpp = mock_file_hpp
        self.file_template_hpp = file_template_hpp
        self.mock_file_cpp = mock_file_cpp
        self.file_template_cpp = file_template_cpp
        self.cursor = self.__parse(files, args).cursor

    def generate(self):
        mock_methods = {}
        self.__get_mock_methods(self.cursor, mock_methods)
        for expr, mock_methods in mock_methods.items():
            if len(mock_methods) > 0:
                self.file_template_hpp != "" and self.__generate_file(expr, mock_methods, "hpp", self.file_template_hpp)
                self.file_template_cpp != "" and self.__generate_file(expr, mock_methods, "cpp", self.file_template_cpp)
        return 0

def main(args):
    clang_args = None
    args_split = [i for i, arg in enumerate(args) if arg == "--"]
    if args_split:
        args, clang_args = args[:args_split[0]], args[args_split[0] + 1:]

    default_config = "gmock.conf"

    parser = OptionParser(usage="usage: %prog [options] files...")
    parser.add_option("-c", "--config", dest="config", default=default_config, help="config FILE (default='gmock.conf')", metavar="FILE")
    parser.add_option("-d", "--dir", dest="path", default=".", help="dir for generated mocks (default='.')", metavar="DIR")
    parser.add_option("-e", "--expr", dest="expr", default="", help="limit to interfaces within expression (default='')", metavar="LIMIT")
    parser.add_option("-l", "--libclang", dest="libclang", default=None, help="path to libclang.so (default=None)", metavar="LIBCLANG")
    (options, args) = parser.parse_args(args)

    if len(args) == 1:
        parser.error("at least one file has to be given")

    config = {}
    with open(options.config, 'r') as file:
        exec(file.read(), config)

    if options.libclang:
      Config.set_library_file(options.libclang)

    return mock_generator(
        files = args[1:],
        args = clang_args,
        expr = options.expr,
        path = options.path,
        mock_file_hpp = config['mock_file_hpp'],
        file_template_hpp = config['file_template_hpp'],
        mock_file_cpp = config['mock_file_cpp'],
        file_template_cpp = config['file_template_cpp']
    ).generate()

if __name__ == "__main__":
    sys.exit(main(sys.argv))

