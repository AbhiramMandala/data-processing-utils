"""JSON / XML / CSV integration utilities (OOP + generators)."""
import csv
import json
import xml.etree.ElementTree as ET
from typing import Any, Dict, Iterator


class JsonXmlConverter:
    """Convert between JSON, XML and CSV. Stdlib only."""

    # -- dict <-> XML --------------------------------------------------
    @staticmethod
    def dict_to_xml(data: Dict, root: str = "record") -> str:
        elem = ET.Element(root)
        JsonXmlConverter._dict_to_elem(elem, data)
        return ET.tostring(elem, encoding="unicode")

    @staticmethod
    def _dict_to_elem(parent: ET.Element, data: Any) -> None:
        if isinstance(data, dict):
            for k, v in data.items():
                child = ET.SubElement(parent, str(k).replace(" ", "_"))
                JsonXmlConverter._dict_to_elem(child, v)
        elif isinstance(data, list):
            for item in data:
                child = ET.SubElement(parent, "item")
                JsonXmlConverter._dict_to_elem(child, item)
        elif data is None:
            parent.text = ""
        else:
            parent.text = str(data)

    @staticmethod
    def xml_to_dict(xml_str: str) -> Dict:
        root = ET.fromstring(xml_str)
        return {root.tag: JsonXmlConverter._elem_to_dict(root)}

    @staticmethod
    def _elem_to_dict(elem: ET.Element) -> Any:
        children = list(elem)
        if not children:
            return (elem.text or "").strip()
        items = [JsonXmlConverter._elem_to_dict(c) for c in children]
        tags = [c.tag for c in children]
        if len(set(tags)) == 1 and tags[0] == "item":
            return items  # list container
        out: Dict[str, Any] = {}
        for c in children:
            out[c.tag] = JsonXmlConverter._elem_to_dict(c)
        return out

    # -- JSON <-> XML documents ----------------------------------------
    def json_to_xml_doc(self, data: Any, root: str = "root", item_tag: str = "record") -> str:
        if isinstance(data, list):
            elem = ET.Element(root)
            for row in data:
                child = ET.SubElement(elem, item_tag)
                self._dict_to_elem(child, row)
            return ET.tostring(elem, encoding="unicode")
        return self.dict_to_xml(data if isinstance(data, dict) else {"value": data}, root=root)

    def xml_to_json(self, xml_str: str) -> Any:
        root = ET.fromstring(xml_str)
        children = list(root)
        if children and all(c.tag == children[0].tag for c in children):
            return [self._elem_to_dict(c) for c in children]
        return self._elem_to_dict(root)

    # -- file helpers ---------------------------------------------------
    def json_file_to_xml_file(self, src: str, dst: str, root: str = "root") -> None:
        with open(src, encoding="utf-8") as f:
            data = json.load(f)
        with open(dst, "w", encoding="utf-8") as f:
            f.write(self.json_to_xml_doc(data, root=root))

    def xml_file_to_json_file(self, src: str, dst: str) -> None:
        with open(src, encoding="utf-8") as f:
            xml_str = f.read()
        with open(dst, "w", encoding="utf-8") as f:
            json.dump(self.xml_to_json(xml_str), f, indent=2)

    def csv_file_to_json_file(self, src: str, dst: str) -> int:
        rows = list(self.stream_csv_as_json(src))
        with open(dst, "w", encoding="utf-8") as f:
            json.dump(rows, f, indent=2)
        return len(rows)

    # -- streaming generators -------------------------------------------
    @staticmethod
    def stream_csv_as_json(path: str, encoding: str = "utf-8") -> Iterator[Dict]:
        """Yield each CSV row as a dict (constant memory)."""
        with open(path, newline="", encoding=encoding) as f:
            yield from csv.DictReader(f)

    @staticmethod
    def stream_json_lines(path: str, encoding: str = "utf-8") -> Iterator[Any]:
        """Yield one object per line of a JSON-lines (.jsonl) file."""
        with open(path, encoding=encoding) as f:
            for line in f:
                line = line.strip()
                if line:
                    yield json.loads(line)

    @staticmethod
    def write_json_lines(path: str, records, encoding: str = "utf-8") -> int:
        n = 0
        with open(path, "w", encoding=encoding) as f:
            for rec in records:
                f.write(json.dumps(rec) + "\n")
                n += 1
        return n
