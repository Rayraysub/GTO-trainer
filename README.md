# GTO Trainer 🃏

德州扑克 GTO 多街训练器 — 完整项目版本

## 项目结构

```
gto_trainer/
│
├── app.py              # Flask 后端 + REST API 路由
├── poker_engine.py     # 核心扑克逻辑（发牌、权益计算、GTO建议）
├── database.py         # SQLite 数据库层（训练记录、统计）
├── requirements.txt    # Python 依赖
│
├── templates/
│   ├── index.html      # 主训练页面（随机场景 + 计算工具）
│   └── stats.html      # 统计分析页面
│
└── data/
    └── trainer.db      # SQLite 数据库（自动生成）
```

## 快速启动

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 启动服务器
python app.py

# 3. 浏览器访问
http://localhost:5000
```

## API 接口说明

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/session/start | 开始训练会话 |
| POST | /api/session/end   | 结束会话并返回总结 |
| GET  | /api/scenario/random?street=flop | 随机生成训练场景 |
| POST | /api/scenario/decide | 提交决策，返回是否正确 |
| POST | /api/calc/pot_odds  | 计算底池赔率 |
| POST | /api/calc/equity    | 蒙特卡洛权益计算 |
| POST | /api/calc/ev        | EV 计算 |
| GET  | /api/stats          | 获取全部统计数据 |

## 各文件职责

### poker_engine.py
- `Deck` / `Card`：标准52张牌，洗牌/发牌
- `evaluate_5()` + `best_hand_from_7()`：手牌评估（高牌到皇家同花顺）
- `calc_equity()`：蒙特卡洛模拟权益（默认5000次）
- `pot_odds()` + `calc_ev()`：GTO数学计算
- `random_scenario()`：随机生成场景 + 简化GTO建议
- `simple_gto_advice()`：基于规则的GTO近似（Preflop范围 + 翻后手牌强度）

### database.py
- `init_db()`：建表
- `save_decision()`：保存每次决策记录
- `get_overall_stats()`：返回总体/街道/位置/手牌统计
- `get_session_stats()`：单场次统计

### app.py
- Flask 路由，连接引擎和数据库
- 提供 JSON API 给前端调用

## 扩展方向

1. **更精确的GTO范围**：导入 PioSOLVER / GTO+ 的输出文件替换 `simple_gto_advice()`
2. **多玩家支持**：加入用户账号系统（Flask-Login）
3. **手牌历史复盘**：保存完整手牌过程，支持回放
4. **范围可视化**：在前端渲染13×13手牌网格
