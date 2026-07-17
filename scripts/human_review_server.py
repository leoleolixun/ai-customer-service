#!/usr/bin/env python3
# ruff: noqa: E501, RUF001
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import socketserver
import tempfile
import threading
from collections import Counter
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

REVIEW_FIELDS = (
    "reviewer",
    "factually_correct",
    "citations_supported",
    "severe_error",
    "notes",
)
VALID_CATEGORIES = {
    "answerable",
    "no_answer",
    "conflict_or_stale",
    "handoff",
    "prompt_injection_or_unauthorized",
}


PAGE = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>V1 人工复核</title>
  <style nonce="__NONCE__">
    :root {
      color-scheme: light;
      --bg: #f4f6f8;
      --surface: #ffffff;
      --ink: #17202a;
      --muted: #667085;
      --line: #d8dee7;
      --blue: #155eef;
      --blue-soft: #eef4ff;
      --green: #067647;
      --green-soft: #ecfdf3;
      --red: #b42318;
      --red-soft: #fef3f2;
      --amber: #b54708;
      --amber-soft: #fffaeb;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    * { box-sizing: border-box; }
    body { margin: 0; color: var(--ink); background: var(--bg); font-size: 14px; }
    button, input, textarea, select { font: inherit; letter-spacing: 0; }
    button { cursor: pointer; }
    button:disabled { cursor: not-allowed; opacity: .55; }
    .app { min-height: 100vh; display: grid; grid-template-rows: auto 1fr; }
    header {
      position: sticky; top: 0; z-index: 10; min-height: 64px; padding: 10px 18px;
      display: flex; align-items: center; gap: 16px; flex-wrap: wrap;
      color: #fff; background: #182230; border-bottom: 1px solid #344054;
    }
    h1 { margin: 0; font-size: 18px; font-weight: 700; }
    .release { color: #cbd5e1; font-size: 12px; }
    .progress-wrap { min-width: 210px; margin-left: auto; }
    .progress-label { display: flex; justify-content: space-between; margin-bottom: 5px; color: #e2e8f0; font-size: 12px; }
    .progress-track { width: 100%; height: 6px; display: block; overflow: hidden; border: 0; border-radius: 3px; appearance: none; background: #475467; }
    .progress-track::-webkit-progress-bar { background: #475467; }
    .progress-track::-webkit-progress-value { background: #32d583; transition: width .2s ease; }
    .progress-track::-moz-progress-bar { background: #32d583; }
    .save-state { min-width: 92px; color: #d0d5dd; font-size: 12px; text-align: right; }
    .layout { min-width: 0; display: grid; grid-template-columns: 280px minmax(0, 1fr); }
    aside { border-right: 1px solid var(--line); background: var(--surface); min-height: calc(100vh - 64px); }
    .aside-tools { position: sticky; top: 64px; padding: 14px; background: var(--surface); border-bottom: 1px solid var(--line); }
    label.field-label { display: block; margin-bottom: 6px; color: #344054; font-size: 12px; font-weight: 700; }
    label.filter-label { margin-top: 10px; }
    input, select, textarea {
      width: 100%; border: 1px solid #98a2b3; border-radius: 5px; color: var(--ink); background: #fff;
      outline: none;
    }
    input, select { height: 36px; padding: 0 10px; }
    textarea { min-height: 92px; resize: vertical; padding: 9px 10px; line-height: 1.5; }
    input:focus, select:focus, textarea:focus { border-color: var(--blue); box-shadow: 0 0 0 3px rgba(21,94,239,.12); }
    .reviewer-row { display: grid; grid-template-columns: 1fr auto; gap: 6px; }
    .case-list { padding: 7px; display: grid; gap: 3px; }
    .case-button {
      width: 100%; min-height: 42px; padding: 7px 9px; display: grid; grid-template-columns: 22px 1fr auto;
      align-items: center; gap: 7px; border: 1px solid transparent; border-radius: 5px;
      color: #344054; background: transparent; text-align: left;
    }
    .case-button:hover { background: #f8fafc; }
    .case-button.active { color: #164c96; background: var(--blue-soft); border-color: #b2ccff; }
    .case-number {
      width: 22px; height: 22px; display: inline-grid; place-items: center;
      border-radius: 50%; color: #475467; background: #eaecf0; font-size: 11px; font-weight: 700;
    }
    .case-button.complete .case-number { color: var(--green); background: var(--green-soft); }
    .case-title { overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
    .category-code { color: var(--muted); font-size: 10px; }
    main { min-width: 0; padding: 18px 22px 96px; }
    .main-inner { max-width: 1180px; margin: 0 auto; }
    .case-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; margin-bottom: 14px; }
    .case-head h2 { margin: 3px 0 0; font-size: 20px; line-height: 1.35; }
    .meta { display: flex; gap: 6px; flex-wrap: wrap; }
    .tag { padding: 3px 7px; border: 1px solid var(--line); border-radius: 4px; color: #475467; background: #fff; font-size: 11px; }
    .tag.risk-high { color: var(--red); border-color: #fecdca; background: var(--red-soft); }
    .tag.risk-medium { color: var(--amber); border-color: #fedf89; background: var(--amber-soft); }
    .panel { margin-bottom: 14px; border-top: 1px solid var(--line); padding-top: 14px; }
    .panel-title { margin: 0 0 8px; color: #344054; font-size: 12px; font-weight: 800; text-transform: uppercase; }
    .content-box { margin: 0; padding: 12px; border-left: 3px solid #98a2b3; background: #fff; line-height: 1.65; white-space: pre-wrap; overflow-wrap: anywhere; }
    .question { border-left-color: var(--blue); font-size: 16px; font-weight: 650; }
    .evidence-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
    .evidence-item { margin-bottom: 8px; padding: 10px; border: 1px solid var(--line); border-radius: 5px; background: #fff; }
    .evidence-item:last-child { margin-bottom: 0; }
    .evidence-title { margin-bottom: 5px; color: #344054; font-weight: 750; }
    .evidence-id { color: var(--muted); font-size: 11px; }
    .evidence-content { margin-top: 6px; line-height: 1.55; white-space: pre-wrap; overflow-wrap: anywhere; }
    .empty { padding: 12px; border: 1px dashed #98a2b3; color: var(--muted); background: #fff; text-align: center; }
    .review-section { margin-top: 18px; padding-top: 18px; border-top: 2px solid #98a2b3; }
    .review-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; }
    .decision { min-width: 0; }
    .decision-title { min-height: 34px; margin-bottom: 6px; color: #344054; font-weight: 700; }
    .required { color: var(--red); }
    .segments { display: grid; grid-template-columns: repeat(3, 1fr); }
    .segments.two { grid-template-columns: repeat(2, 1fr); }
    .segment {
      min-height: 38px; border: 1px solid #98a2b3; border-right-width: 0; color: #344054; background: #fff;
    }
    .segment:first-child { border-radius: 5px 0 0 5px; }
    .segment:last-child { border-right-width: 1px; border-radius: 0 5px 5px 0; }
    .segment.selected-yes { color: var(--green); background: var(--green-soft); border-color: #6ce9a6; }
    .segment.selected-no { color: var(--red); background: var(--red-soft); border-color: #fda29b; }
    .segment.selected-na { color: #475467; background: #f2f4f7; }
    .notes { margin-top: 14px; }
    .footer-actions {
      position: fixed; z-index: 8; right: 0; bottom: 0; left: 280px; min-height: 68px; padding: 12px 22px;
      display: flex; align-items: center; justify-content: space-between; gap: 10px;
      border-top: 1px solid var(--line); background: rgba(255,255,255,.96); backdrop-filter: blur(8px);
    }
    .actions { display: flex; gap: 8px; }
    .btn { min-height: 38px; padding: 0 13px; border: 1px solid #98a2b3; border-radius: 5px; color: #344054; background: #fff; font-weight: 700; }
    .btn:hover { background: #f8fafc; }
    .btn.primary { color: #fff; border-color: var(--blue); background: var(--blue); }
    .btn.primary:hover { background: #004eeb; }
    .btn.success { color: #fff; border-color: var(--green); background: var(--green); }
    .validation { color: var(--muted); font-size: 12px; }
    .validation.error { color: var(--red); font-weight: 700; }
    .validation.ok { color: var(--green); font-weight: 700; }
    .toast {
      position: fixed; z-index: 20; top: 74px; right: 18px; max-width: min(420px, calc(100vw - 36px));
      padding: 10px 12px; border: 1px solid var(--line); border-radius: 5px; color: #344054; background: #fff;
      box-shadow: 0 8px 24px rgba(16,24,40,.15); opacity: 0; transform: translateY(-8px); pointer-events: none;
      transition: .18s ease;
    }
    .toast.show { opacity: 1; transform: translateY(0); }
    .toast.error { color: var(--red); border-color: #fda29b; background: var(--red-soft); }
    @media (max-width: 820px) {
      header { min-height: auto; padding: 10px 12px; }
      .progress-wrap { order: 3; width: 100%; margin-left: 0; }
      .save-state { margin-left: auto; }
      .layout { display: block; }
      aside { min-height: 0; border-right: 0; border-bottom: 1px solid var(--line); }
      .aside-tools { position: static; padding: 10px 12px; }
      .case-list { display: flex; overflow-x: auto; padding: 7px 12px; }
      .case-button { flex: 0 0 50px; min-height: 40px; display: block; padding: 8px; text-align: center; }
      .case-title, .category-code { display: none; }
      main { padding: 14px 12px 20px; }
      .case-head { display: block; }
      .case-head h2 { margin-bottom: 10px; font-size: 18px; }
      .evidence-grid, .review-grid { grid-template-columns: 1fr; }
      .decision-title { min-height: 0; }
      .footer-actions { position: static; min-height: 0; padding: 10px 12px 14px; flex-wrap: wrap; }
      .validation { width: 100%; order: 2; }
      .actions { width: 100%; }
      .actions .btn { flex: 1; padding: 0 8px; }
      .btn.success { flex: 1; }
    }
  </style>
</head>
<body>
  <div class="app">
    <header>
      <div>
        <h1>V1 独立人工复核</h1>
        <div class="release">候选 __CANDIDATE__ · 工作表 __WORKSHEET_SHA__ · 30 条固定样本</div>
      </div>
      <div class="progress-wrap" aria-label="复核进度">
        <div class="progress-label"><span>完成进度</span><strong id="progressText">0 / 30</strong></div>
        <progress class="progress-track" id="progressBar" value="0" max="30"></progress>
      </div>
      <div class="save-state" id="saveState">载入中</div>
    </header>
    <div class="layout">
      <aside>
        <div class="aside-tools">
          <label class="field-label" for="reviewerName">独立复核人</label>
          <div class="reviewer-row">
            <input id="reviewerName" maxlength="200" autocomplete="name" placeholder="姓名或标识">
            <button class="btn" id="applyReviewer" type="button">应用全部</button>
          </div>
          <label class="field-label filter-label" for="categoryFilter">样本分类</label>
          <select id="categoryFilter">
            <option value="all">全部分类</option>
            <option value="answerable">可回答</option>
            <option value="no_answer">无答案</option>
            <option value="conflict_or_stale">冲突或过期</option>
            <option value="handoff">人工接管</option>
            <option value="prompt_injection_or_unauthorized">注入或越权</option>
          </select>
        </div>
        <nav class="case-list" id="caseList" aria-label="复核样本"></nav>
      </aside>
      <main>
        <div class="main-inner">
          <div class="case-head">
            <div>
              <div class="meta" id="caseMeta"></div>
              <h2 id="caseId">载入中</h2>
            </div>
          </div>
          <section class="panel">
            <h3 class="panel-title">用户问题</h3>
            <div class="content-box question" id="question"></div>
          </section>
          <section class="panel">
            <h3 class="panel-title">模型回答</h3>
            <pre class="content-box" id="answer"></pre>
          </section>
          <div class="evidence-grid">
            <section class="panel">
              <h3 class="panel-title">预期证据</h3>
              <div id="expectedEvidence"></div>
            </section>
            <section class="panel">
              <h3 class="panel-title">回答引用证据</h3>
              <div id="citedEvidence"></div>
            </section>
          </div>
          <section class="review-section">
            <div class="review-grid">
              <div class="decision">
                <div class="decision-title">事实是否正确 <span class="required" id="factRequired">*</span></div>
                <div class="segments" id="factControls"></div>
              </div>
              <div class="decision">
                <div class="decision-title">引用是否支持回答 <span class="required" id="citationRequired">*</span></div>
                <div class="segments" id="citationControls"></div>
              </div>
              <div class="decision">
                <div class="decision-title">是否存在严重错误 <span class="required">*</span></div>
                <div class="segments two" id="severeControls"></div>
              </div>
            </div>
            <div class="notes">
              <label class="field-label" for="notes">复核备注</label>
              <textarea id="notes" maxlength="5000" placeholder="记录判断依据或发现的问题"></textarea>
            </div>
          </section>
        </div>
      </main>
    </div>
    <div class="footer-actions">
      <div class="actions">
        <button class="btn" id="previous" type="button">上一条</button>
        <button class="btn primary" id="save" type="button">保存</button>
        <button class="btn" id="next" type="button">下一条</button>
      </div>
      <div class="validation" id="validation">等待复核</div>
      <button class="btn success" id="finalize" type="button">检查完成度</button>
    </div>
    <div class="toast" id="toast" role="status"></div>
  </div>
  <script nonce="__NONCE__">
    const WRITE_TOKEN = "__TOKEN__";
    const categories = {
      answerable: "可回答",
      no_answer: "无答案",
      conflict_or_stale: "冲突或过期",
      handoff: "人工接管",
      prompt_injection_or_unauthorized: "注入或越权"
    };
    const state = { records: [], index: 0, saving: false, dirty: false, timer: null };
    const $ = (id) => document.getElementById(id);

    function complete(record) {
      const r = record.review;
      if (!r.reviewer.trim() || typeof r.severe_error !== "boolean") return false;
      if (record.category === "answerable") {
        return typeof r.factually_correct === "boolean" && typeof r.citations_supported === "boolean";
      }
      return [r.factually_correct, r.citations_supported].every((v) => v === null || typeof v === "boolean");
    }

    function selectedClass(value, option) {
      if (value !== option) return "";
      if (option === true) return "selected-yes";
      if (option === false) return "selected-no";
      return "selected-na";
    }

    function makeDecision(container, field, includeNA) {
      container.replaceChildren();
      const record = state.records[state.index];
      const options = includeNA
        ? [[true, "是"], [false, "否"], [null, "不适用"]]
        : [[true, "是"], [false, "否"]];
      container.classList.toggle("two", !includeNA);
      for (const [value, label] of options) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = `segment ${selectedClass(record.review[field], value)}`;
        button.textContent = label;
        button.setAttribute("aria-pressed", String(record.review[field] === value));
        button.addEventListener("click", () => {
          record.review[field] = value;
          markDirty();
          render();
          scheduleSave();
        });
        container.appendChild(button);
      }
    }

    function addTag(parent, text, extraClass = "") {
      const span = document.createElement("span");
      span.className = `tag ${extraClass}`.trim();
      span.textContent = text;
      parent.appendChild(span);
    }

    function renderEvidence(container, evidence) {
      container.replaceChildren();
      if (!evidence.length) {
        const empty = document.createElement("div");
        empty.className = "empty";
        empty.textContent = "无证据";
        container.appendChild(empty);
        return;
      }
      for (const item of evidence) {
        const wrapper = document.createElement("article");
        wrapper.className = "evidence-item";
        const title = document.createElement("div");
        title.className = "evidence-title";
        title.textContent = item.title;
        const id = document.createElement("div");
        id.className = "evidence-id";
        id.textContent = `${item.source_id} · ${item.status}`;
        const content = document.createElement("div");
        content.className = "evidence-content";
        content.textContent = item.content;
        wrapper.append(title, id, content);
        container.appendChild(wrapper);
      }
    }

    function visibleIndexes() {
      const filter = $("categoryFilter").value;
      return state.records.map((record, index) => ({record, index}))
        .filter(({record}) => filter === "all" || record.category === filter)
        .map(({index}) => index);
    }

    function renderList() {
      const list = $("caseList");
      list.replaceChildren();
      for (const index of visibleIndexes()) {
        const record = state.records[index];
        const button = document.createElement("button");
        button.type = "button";
        button.className = `case-button${index === state.index ? " active" : ""}${complete(record) ? " complete" : ""}`;
        button.title = record.question;
        const number = document.createElement("span");
        number.className = "case-number";
        number.textContent = String(index + 1);
        const title = document.createElement("span");
        title.className = "case-title";
        title.textContent = record.question;
        const category = document.createElement("span");
        category.className = "category-code";
        category.textContent = categories[record.category];
        button.append(number, title, category);
        button.addEventListener("click", async () => {
          await saveIfDirty();
          state.index = index;
          render();
        });
        list.appendChild(button);
      }
    }

    function render() {
      if (!state.records.length) return;
      const record = state.records[state.index];
      $("caseId").textContent = record.case_id;
      $("question").textContent = record.question;
      $("answer").textContent = record.answer;
      $("notes").value = record.review.notes;
      if (record.review.reviewer && !$("reviewerName").value) $("reviewerName").value = record.review.reviewer;
      const meta = $("caseMeta");
      meta.replaceChildren();
      addTag(meta, categories[record.category]);
      addTag(meta, record.tenant_id);
      addTag(meta, record.application_id);
      const risk = record.risk?.level || "unknown";
      addTag(meta, `风险 ${risk}`, `risk-${risk}`);
      renderEvidence($("expectedEvidence"), record.expected_evidence || []);
      renderEvidence($("citedEvidence"), record.cited_evidence || []);
      const answerable = record.category === "answerable";
      $("factRequired").hidden = !answerable;
      $("citationRequired").hidden = !answerable;
      makeDecision($("factControls"), "factually_correct", !answerable);
      makeDecision($("citationControls"), "citations_supported", !answerable);
      makeDecision($("severeControls"), "severe_error", false);
      renderList();
      updateProgress();
    }

    function updateProgress() {
      const completed = state.records.filter(complete).length;
      const total = state.records.length;
      $("progressText").textContent = `${completed} / ${total}`;
      $("progressBar").max = total;
      $("progressBar").value = completed;
      $("validation").textContent = completed === total ? "全部样本字段完整" : `还有 ${total - completed} 条未完成`;
      $("validation").className = `validation ${completed === total ? "ok" : ""}`;
    }

    function markDirty() {
      state.dirty = true;
      $("saveState").textContent = "未保存";
    }

    function scheduleSave() {
      clearTimeout(state.timer);
      state.timer = setTimeout(() => save(false), 650);
    }

    async function save(finalize = false) {
      clearTimeout(state.timer);
      if (state.saving) return false;
      state.saving = true;
      $("saveState").textContent = "保存中";
      try {
        const response = await fetch("/api/reviews", {
          method: "POST",
          headers: {"Content-Type": "application/json", "X-Review-Token": WRITE_TOKEN},
          body: JSON.stringify({
            finalize,
            reviews: state.records.map(({case_id, review}) => ({case_id, review}))
          })
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || "保存失败");
        state.dirty = false;
        $("saveState").textContent = "已保存";
        updateProgress();
        if (finalize) {
          $("validation").textContent = result.ready ? "30 条复核已通过完整性检查" : result.message;
          $("validation").className = `validation ${result.ready ? "ok" : "error"}`;
          showToast(result.ready ? "复核工作表已完整，可执行正式合并" : result.message, !result.ready);
        }
        return true;
      } catch (error) {
        $("saveState").textContent = "保存失败";
        showToast(error.message, true);
        return false;
      } finally {
        state.saving = false;
      }
    }

    async function saveIfDirty() {
      return !state.dirty || await save(false);
    }

    function showToast(message, error = false) {
      const toast = $("toast");
      toast.textContent = message;
      toast.className = `toast show${error ? " error" : ""}`;
      setTimeout(() => { toast.className = "toast"; }, 3200);
    }

    function move(delta) {
      const indexes = visibleIndexes();
      const position = indexes.indexOf(state.index);
      const target = indexes[position + delta];
      if (target === undefined) return;
      saveIfDirty().then((saved) => {
        if (saved) { state.index = target; render(); }
      });
    }

    async function load() {
      try {
        const response = await fetch("/api/reviews");
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || "载入失败");
        state.records = result.records;
        $("saveState").textContent = "已载入";
        render();
      } catch (error) {
        $("saveState").textContent = "载入失败";
        showToast(error.message, true);
      }
    }

    $("notes").addEventListener("input", (event) => {
      state.records[state.index].review.notes = event.target.value;
      markDirty();
      scheduleSave();
    });
    $("reviewerName").addEventListener("change", (event) => {
      state.records[state.index].review.reviewer = event.target.value.trim();
      markDirty();
      render();
      scheduleSave();
    });
    $("applyReviewer").addEventListener("click", () => {
      const reviewer = $("reviewerName").value.trim();
      if (!reviewer) { showToast("请先填写独立复核人", true); return; }
      state.records.forEach((record) => { record.review.reviewer = reviewer; });
      markDirty();
      render();
      save(false).then((ok) => { if (ok) showToast("复核人已应用到全部样本"); });
    });
    $("categoryFilter").addEventListener("change", () => {
      const indexes = visibleIndexes();
      if (!indexes.includes(state.index)) state.index = indexes[0] || 0;
      render();
    });
    $("previous").addEventListener("click", () => move(-1));
    $("next").addEventListener("click", () => move(1));
    $("save").addEventListener("click", () => save(false).then((ok) => { if (ok) showToast("已保存"); }));
    $("finalize").addEventListener("click", () => save(true));
    window.addEventListener("beforeunload", (event) => {
      if (state.dirty) { event.preventDefault(); event.returnValue = ""; }
    });
    load();
  </script>
</body>
</html>
"""


class ReviewStore:
    def __init__(self, worksheet: Path) -> None:
        self.worksheet = worksheet.resolve(strict=True)
        self.lock = threading.Lock()
        self.records = self._load()
        self.case_ids = [str(record["case_id"]) for record in self.records]
        self._validate_shape()

    def _load(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for line_number, line in enumerate(
            self.worksheet.read_text(encoding="utf-8").splitlines(), 1
        ):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"line {line_number}: each JSONL value must be an object")
            records.append(value)
        return records

    def _validate_shape(self) -> None:
        if len(self.records) != 30:
            raise ValueError(
                f"worksheet must contain exactly 30 records, found {len(self.records)}"
            )
        if len(set(self.case_ids)) != len(self.case_ids):
            raise ValueError("worksheet contains duplicate case_id values")
        counts = Counter(str(record.get("category")) for record in self.records)
        expected = {
            "answerable": 18,
            "no_answer": 3,
            "conflict_or_stale": 3,
            "handoff": 3,
            "prompt_injection_or_unauthorized": 3,
        }
        if counts != Counter(expected):
            raise ValueError(f"worksheet category allocation is invalid: {dict(counts)}")
        for index, record in enumerate(self.records, 1):
            if record.get("category") not in VALID_CATEGORIES:
                raise ValueError(f"record {index}: unsupported category")
            self._normalize_review(record.get("review"), str(record["category"]), partial=True)

    @staticmethod
    def _normalize_review(value: Any, category: str, *, partial: bool) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise ValueError("review must be an object")
        unknown = set(value) - set(REVIEW_FIELDS)
        if unknown:
            raise ValueError(f"review contains unsupported fields: {', '.join(sorted(unknown))}")
        reviewer = value.get("reviewer", "")
        notes = value.get("notes", "")
        if not isinstance(reviewer, str) or len(reviewer) > 200:
            raise ValueError("reviewer must be a string with at most 200 characters")
        if not isinstance(notes, str) or len(notes) > 5000:
            raise ValueError("notes must be a string with at most 5000 characters")
        normalized: dict[str, Any] = {
            "reviewer": reviewer.strip(),
            "notes": notes.strip(),
        }
        for field in ("factually_correct", "citations_supported", "severe_error"):
            field_value = value.get(field)
            if field_value is not None and not isinstance(field_value, bool):
                raise ValueError(f"{field} must be true, false, or null")
            normalized[field] = field_value
        if not partial:
            if not normalized["reviewer"]:
                raise ValueError("reviewer is required")
            if not isinstance(normalized["severe_error"], bool):
                raise ValueError("severe_error is required")
            if category == "answerable":
                if not isinstance(normalized["factually_correct"], bool):
                    raise ValueError("answerable review requires factually_correct")
                if not isinstance(normalized["citations_supported"], bool):
                    raise ValueError("answerable review requires citations_supported")
        return normalized

    def _status(self) -> dict[str, Any]:
        incomplete: list[str] = []
        completed_by_category: Counter[str] = Counter()
        for record in self.records:
            try:
                self._normalize_review(record["review"], str(record["category"]), partial=False)
            except ValueError:
                incomplete.append(str(record["case_id"]))
            else:
                completed_by_category[str(record["category"])] += 1
        return {
            "total": len(self.records),
            "completed": len(self.records) - len(incomplete),
            "incomplete_case_ids": incomplete,
            "completed_by_category": dict(completed_by_category),
            "ready": not incomplete,
        }

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return {"records": self.records, "status": self._status()}

    def save(self, updates: Any, *, finalize: bool) -> dict[str, Any]:
        if not isinstance(updates, list) or len(updates) != len(self.records):
            raise ValueError(f"reviews must contain exactly {len(self.records)} records")
        indexed: dict[str, dict[str, Any]] = {}
        for update in updates:
            if not isinstance(update, dict) or set(update) != {"case_id", "review"}:
                raise ValueError("each update must contain only case_id and review")
            case_id = update.get("case_id")
            if not isinstance(case_id, str) or case_id in indexed:
                raise ValueError("case_id must be unique and non-empty")
            indexed[case_id] = update
        if set(indexed) != set(self.case_ids):
            raise ValueError("review case_ids do not match the worksheet")

        with self.lock:
            next_records: list[dict[str, Any]] = []
            for original in self.records:
                case_id = str(original["case_id"])
                replacement = dict(original)
                replacement["review"] = self._normalize_review(
                    indexed[case_id]["review"], str(original["category"]), partial=True
                )
                next_records.append(replacement)
            self.records = next_records
            status = self._status()
            if finalize and not status["ready"]:
                status["message"] = f"还有 {len(status['incomplete_case_ids'])} 条未满足完整性规则"
            elif finalize:
                status["message"] = "all reviews are complete"
            self._atomic_write()
            return status

    def _atomic_write(self) -> None:
        payload = "".join(
            json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
            for record in self.records
        )
        fd, temporary_name = tempfile.mkstemp(
            prefix=f".{self.worksheet.name}.", suffix=".tmp", dir=self.worksheet.parent
        )
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, self.worksheet)
            directory_fd = os.open(self.worksheet.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except Exception:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass
            raise


class ReviewHandler(BaseHTTPRequestHandler):
    server: ReviewServer

    def log_message(self, format: str, *args: Any) -> None:
        print(f"{self.address_string()} - {format % args}")

    def _headers(self, status: HTTPStatus, content_type: str, length: int) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            f"default-src 'none'; style-src 'nonce-{self.server.nonce}'; "
            f"script-src 'nonce-{self.server.nonce}'; connect-src 'self'; "
            "img-src 'self' data:; base-uri 'none'; frame-ancestors 'none'",
        )
        self.end_headers()

    def _json(self, status: HTTPStatus, value: Any) -> None:
        body = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self._headers(status, "application/json; charset=utf-8", len(body))
        self.wfile.write(body)

    def _same_origin(self) -> bool:
        host = self.headers.get("Host", "")
        if host not in {
            f"127.0.0.1:{self.server.server_port}",
            f"localhost:{self.server.server_port}",
        }:
            return False
        origin = self.headers.get("Origin")
        return origin in {
            None,
            f"http://127.0.0.1:{self.server.server_port}",
            f"http://localhost:{self.server.server_port}",
        }

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if not self._same_origin():
            self._json(HTTPStatus.FORBIDDEN, {"error": "invalid origin"})
            return
        if path == "/":
            body = self.server.page().encode("utf-8")
            self._headers(HTTPStatus.OK, "text/html; charset=utf-8", len(body))
            self.wfile.write(body)
            return
        if path == "/api/reviews":
            self._json(HTTPStatus.OK, self.server.store.snapshot())
            return
        if path == "/api/health":
            self._json(HTTPStatus.OK, {"status": "ok"})
            return
        self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def do_HEAD(self) -> None:
        path = urlparse(self.path).path
        if not self._same_origin():
            self._headers(HTTPStatus.FORBIDDEN, "application/json; charset=utf-8", 0)
            return
        if path == "/":
            body = self.server.page().encode("utf-8")
            self._headers(HTTPStatus.OK, "text/html; charset=utf-8", len(body))
            return
        if path in {"/api/reviews", "/api/health"}:
            self._headers(HTTPStatus.OK, "application/json; charset=utf-8", 0)
            return
        self._headers(HTTPStatus.NOT_FOUND, "application/json; charset=utf-8", 0)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path != "/api/reviews":
            self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        if not self._same_origin() or not secrets.compare_digest(
            self.headers.get("X-Review-Token", ""), self.server.write_token
        ):
            self._json(HTTPStatus.FORBIDDEN, {"error": "invalid write authorization"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._json(HTTPStatus.BAD_REQUEST, {"error": "invalid content length"})
            return
        if length < 2 or length > 1_000_000:
            self._json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "invalid request size"})
            return
        try:
            value = json.loads(self.rfile.read(length))
            if not isinstance(value, dict) or set(value) != {"finalize", "reviews"}:
                raise ValueError("body must contain only finalize and reviews")
            if not isinstance(value["finalize"], bool):
                raise ValueError("finalize must be a boolean")
            status = self.server.store.save(value["reviews"], finalize=value["finalize"])
        except (json.JSONDecodeError, ValueError) as exc:
            self._json(HTTPStatus.UNPROCESSABLE_ENTITY, {"error": str(exc)})
            return
        self._json(HTTPStatus.OK, status)


class ReviewServer(ThreadingHTTPServer):
    daemon_threads = True

    def server_bind(self) -> None:
        # HTTPServer performs a reverse DNS lookup here, which can block on a
        # disconnected development machine. The review tool only binds locally.
        socketserver.TCPServer.server_bind(self)
        self.server_name = str(self.server_address[0])
        self.server_port = int(self.server_address[1])

    def __init__(
        self,
        address: tuple[str, int],
        store: ReviewStore,
        *,
        candidate: str,
        worksheet_sha256: str,
    ) -> None:
        super().__init__(address, ReviewHandler)
        self.store = store
        self.candidate = candidate
        self.worksheet_sha256 = worksheet_sha256
        self.write_token = secrets.token_urlsafe(32)
        self.nonce = secrets.token_urlsafe(18)

    def page(self) -> str:
        return (
            PAGE.replace("__NONCE__", self.nonce)
            .replace("__TOKEN__", self.write_token)
            .replace("__CANDIDATE__", self.candidate)
            .replace("__WORKSHEET_SHA__", self.worksheet_sha256[:12])
        )


def worksheet_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_expected_sha256(actual: str, expected: str | None) -> None:
    if expected is None:
        return
    normalized = expected.strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", normalized):
        raise ValueError("expected worksheet SHA256 must contain exactly 64 hexadecimal characters")
    if not secrets.compare_digest(actual.lower(), normalized):
        raise ValueError(f"worksheet SHA256 mismatch: expected {normalized}, calculated {actual}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the local V1 human-review worksheet.")
    parser.add_argument("--worksheet", type=Path, required=True)
    parser.add_argument("--candidate", required=True, help="frozen Git commit under review")
    parser.add_argument(
        "--expected-sha256",
        help="optional expected worksheet SHA256; startup fails when it does not match",
    )
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        raise SystemExit("port must be between 1 and 65535")
    try:
        store = ReviewStore(args.worksheet)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(f"cannot load worksheet: {exc}") from exc
    candidate = args.candidate.strip()
    if not re.fullmatch(r"[0-9a-fA-F]{7,40}", candidate):
        raise SystemExit("candidate must be a 7 to 40 character hexadecimal Git commit")
    digest = worksheet_sha256(store.worksheet)
    try:
        verify_expected_sha256(digest, args.expected_sha256)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    server = ReviewServer(
        ("127.0.0.1", args.port),
        store,
        candidate=candidate,
        worksheet_sha256=digest,
    )
    print(f"Human review: http://127.0.0.1:{args.port}/")
    print(f"Candidate: {candidate}")
    print(f"Worksheet: {store.worksheet}")
    print(f"Worksheet SHA256: {digest}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
