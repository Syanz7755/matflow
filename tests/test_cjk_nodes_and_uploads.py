"""Chinese text in node labels, node keys and text uploads."""
import unittest

from tests.test_api_contract_v11 import WorkspaceHttpTestCase

from backend.keys import label_from_message, node_key_from_label

CHINESE = "对一份阻抗频率扫描做基础 EIS 质量检查，并绘制 Nyquist 图。"


class KeyAndLabelTests(unittest.TestCase):
    def test_ascii_labels_keep_their_historical_keys(self):
        self.assertEqual(node_key_from_label("Basic EIS QC"), "basic_eis_qc")
        self.assertEqual(node_key_from_label("  XRD-peak (v2) "), "xrd_peak_v2")
        self.assertEqual(node_key_from_label("already_a_key"), "already_a_key")

    def test_pure_chinese_label_gets_a_stable_nonempty_key(self):
        key = node_key_from_label("阻抗质检")
        self.assertRegex(key, r"^node_[0-9a-f]{8}$")
        self.assertEqual(key, node_key_from_label("阻抗质检"))
        self.assertNotEqual(key, node_key_from_label("衰减分析"))

    def test_blank_label_has_no_key(self):
        self.assertEqual(node_key_from_label("  "), "")

    def test_label_keeps_chinese_and_is_capped_by_characters(self):
        label = label_from_message(CHINESE)
        self.assertEqual(label, "对一份阻抗频率扫描做基础 EIS 质量检查并绘制 Nyquist 图")
        self.assertEqual(len(label_from_message("阻" * 100)), 48)
        self.assertEqual(label_from_message("！？。"), "Derived Analysis")
        self.assertEqual(label_from_message("run   basic\nEIS"), "run basicEIS")


class NodeLibraryHttpTests(WorkspaceHttpTestCase):
    def test_prompt_build_keeps_the_chinese_label_and_a_usable_key(self):
        body = self.client.post("/api/node-library/prompt-build", json={"message": "阻抗质检流程"}).json()
        self.assertEqual(body["node"]["label"], "阻抗质检流程")
        self.assertEqual(body["key"], node_key_from_label("阻抗质检流程"))
        created = self.client.post("/api/node-library", json={"node": body["node"]})
        self.assertEqual(created.status_code, 200, created.text)
        self.assertEqual(created.json()["key"], body["key"])

    def test_ascii_prompt_build_key_is_unchanged(self):
        body = self.client.post("/api/node-library/prompt-build", json={"message": "Basic EIS QC"}).json()
        self.assertEqual(body["key"], "basic_eis_qc")


class TextUploadTests(WorkspaceHttpTestCase):
    def inspect(self, name, content):
        record = self.runtime.import_dataset(name, content, "application/octet-stream")
        response = self.client.get(f"/api/uploads/{record['id']}")
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_chinese_markdown_is_accepted_and_read_as_text(self):
        inspected = self.inspect("说明.md", f"# 实验记录\n\n{CHINESE}\n".encode("utf-8"))
        self.assertEqual(inspected["kind"], "text")
        self.assertIn("阻抗", inspected["preview"])

    def test_chinese_prose_txt_is_text_not_binary(self):
        inspected = self.inspect("notes.txt", CHINESE.encode("utf-8-sig"))
        self.assertEqual(inspected["kind"], "text")
        self.assertTrue(inspected["preview"].startswith("对一份"))

    def test_tabular_txt_with_chinese_headers_is_still_a_table(self):
        inspected = self.inspect("data.txt", "频率,阻抗\n1,2\n3,4\n".encode("utf-8"))
        self.assertEqual(inspected["kind"], "table")
        self.assertEqual([column["name"] for column in inspected["columns"]], ["频率", "阻抗"])

    def test_non_utf8_txt_stays_binary(self):
        self.assertEqual(self.inspect("x.txt", "阻抗".encode("gbk") * 3)["kind"], "binary")

    def test_markdown_upload_endpoint_does_not_reject_md(self):
        response = self.client.post("/api/uploads", files={"files": ("a.md", "# 标题".encode("utf-8"), "text/markdown")})
        self.assertEqual(response.status_code, 200, response.text)


if __name__ == "__main__":
    unittest.main()
