---
source: 微信公众号
author: 数字Q
title: 推荐好用的 PPT skill，同时开源了一个PPT编辑skill
url: https://mp.weixin.qq.com/s/6mWiXclGmAYrsMflZIZHsQ
date: 2026-07-11
tags: [PPT, skill, AI工具, 幻灯片, 开源]
---

# PPT Skill 推荐与开源 PPT 编辑 Skill

## 市面 PPT Skill 分类

### 第一类：HTML 网页 PPT（单文件HTML，浏览器全屏放映）
- **guizang-ppt-skill**（归藏）：电子杂志风 + 瑞士国际主义风，22种注册版式（S01-S22），一致性高
- **html-ppt-skill**（lewislulu）：24套主题、31种版式、20多种动画
- **frontend-slides**（zarazhangrui）：先生成3个视觉预览再挑，10套风格，反对"AI味"
- 优点：视觉表现力最强
- 缺点：生成后不能直接编辑文本

### 第二类：原生 PPTX（真正的.pptx文件）
- **ppt-master**（hugohe3）：生成原生形状和动画，每个文本框/色块是真元件，可在PowerPoint中编辑
- **baoyu-slide-deck**（宝玉）：图片型幻灯片，视觉精致但不可编辑
- 优点：可编辑
- 缺点：视觉上限被PowerPoint限制

### 第三类：HTML 和 PPTX 之间的桥梁
- **huashu-design**（花叔）：HTML原生设计skill，幻灯片只是能力之一，20条设计哲学，5维评审标准，可导出MP4

## 核心痛点
生成能力很强，但"微调"很原始。改一个字可能要重新整页生成，或者手改大段HTML代码。

## 开源项目：可编辑的 HTML PPT Skill
作者开源了一个**后处理工具**，不是生成器，而是让生成好的HTML PPT能被可视化微调。

### 功能
- 单击选中，双击改文字（可改单个字）
- 拖本体挪位置
- 右侧面板改字号/字重/颜色/行高/宽高
- 复制、删除、上下调换组件
- 导出纯净版（不含编辑器代码）
- 全屏预览

### 设计思路
做成skill而非独立软件，因为skill是活的，大模型能自己判断HTML结构该调哪个工具。

## 适用场景
- 先有HTML PPT（来自上述任一生成skill）
- 需要微调文字/位置/样式
- 不想为了改一个字重新生成整页
