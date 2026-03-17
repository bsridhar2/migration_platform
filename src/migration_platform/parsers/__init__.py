"""Parsers package — Strategy pattern for file-type specific chunking."""
from migration_platform.parsers.base import BaseParser, ParserRegistry
from migration_platform.parsers.java_parser import JavaParser
from migration_platform.parsers.jsp_parser import JspParser
from migration_platform.parsers.js_parser import JsParser
from migration_platform.parsers.xml_parser import XmlParser

__all__ = [
    "BaseParser",
    "ParserRegistry",
    "JavaParser",
    "JspParser",
    "JsParser",
    "XmlParser",
]
