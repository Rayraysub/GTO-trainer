const I18N = {
  zh: {
    // nav
    nav_train: '训练',
    nav_stats: '统计分析',
    nav_info:  '术语词典',

    // session
    btn_start:   '开始训练',
    btn_end:     '结束本轮',
    session_active: '场次 #{{id}} 进行中',

    // filters
    filter_all:     '全部',
    filter_preflop: 'Preflop',
    filter_flop:    'Flop',
    filter_turn:    'Turn',
    filter_river:   'River',

    // stats bar
    stat_total:    '决策总数',
    stat_correct:  '正确',
    stat_pct:      '正确率',
    stat_sessions: '训练场次',

    // opponent
    opp_title:        '对手类型',
    opp_random:       '🎲 随机',
    opp_signal_title: '关键信号',
    opp_exploit_title:'剥削建议',
    opp_key_signals:  '关键信号',
    opp_exploit_btn:  '剥削性分析',

    // scenario
    your_hand:     '你的手牌',
    pot_label:     '底池',
    stack_label:   '筹码',
    preflop_ctx:   '轮到你行动（首轮）',
    postflop_ctx:  '对手 check，轮到你',

    // actions
    action_fold:  '弃牌',
    action_call:  '跟注',
    action_check: '过牌',
    action_raise: '加注',
    action_bet:   '下注',
    action_allin: '全押',
    action_3bet:  '3-Bet',
    action_4bet:  '4-Bet',

    // feedback
    correct_prefix:   '正确！',
    wrong_prefix:     'GTO建议：',
    next_btn:         '下一题 →',
    equity_btn:       '计算真实权益（蒙特卡洛）',
    equity_vs:        'vs 随机范围（{{n}}次模拟）',
    equity_tie:       '平局：{{n}}%',
    exploit_title:    '剥削性分析：',

    // round summary
    round_title:   '本轮总结',
    round_pct_lbl: '正确',
    new_round_btn: '开始新一轮',

    // tools
    tools_title:      'GTO 计算工具',
    tool_odds_title:  '底池赔率',
    tool_ev_title:    'EV 计算器',
    lbl_pot:          '底池',
    lbl_bet:          '对手下注',
    lbl_myeq:         '我的权益',
    lbl_evbet:        '下注额',
    lbl_fold_pct:     '对手弃牌率',
    lbl_called_eq:    '被跟注权益',
    unit_bb:          'bb',
    unit_pct:         '%',
    unit_eq_opt:      '%（可选）',
    odds_needed:      '需要权益',
    odds_ratio:       '底池赔率',
    odds_betpct:      '下注比例',
    odds_good:        '跟注合算（超出{{n}}%）',
    odds_bad:         '跟注不合算（差{{n}}%）',
    ev_bet_lbl:       '下注 EV',
    ev_check_lbl:     '过牌 EV',
    ev_fold_lbl:      '弃牌 EV',
    ev_best:          '最优行动',
    ev_gto_fold:      '对手GTO弃牌率',
    ev_action_bet:    '下注',
    ev_action_check:  '过牌',
    ev_action_fold:   '弃牌',

    // stats page
    stats_overall:    '总体表现',
    stats_by_street:  '各街道正确率',
    stats_by_pos:     '各位置正确率',
    stats_weak:       '⚠️ 薄弱手牌（正确率最低）',
    stats_recent:     '最近决策记录',
    stats_sessions:   '训练场次历史',
    stats_no_data:    '暂无数据',
    stats_no_weak:    '需要至少3次记录才会显示',
    stats_no_recent:  '暂无记录',
    tbl_hand:         '手牌',
    tbl_count:        '练习次数',
    tbl_correct:      '正确',
    tbl_pct:          '正确率',
    tbl_street:       '街道',
    tbl_pos:          '位置',
    tbl_your_action:  '你的行动',
    tbl_gto:          'GTO',
    tbl_result:       '结果',
    tbl_session:      '场次',
    tbl_time:         '时间',
    tbl_decisions:    '题目数',
    result_ok:        '正确',
    result_no:        '错误',

    // street names
    street_preflop: '翻前',
    street_flop:    '翻牌',
    street_turn:    '转牌',
    street_river:   '河牌',

    // info page
    info_title:       '术语词典',
    info_search:      '搜索术语...',
    info_no_results:  '没有找到相关术语',
    info_full_name:   '完整名称',
    info_definition:  '定义',
    info_formula:     '公式 / 计算',
    info_benchmarks:  '高低判断基准',
    info_example:     '实战例子',
    info_cat_all:     '全部',
    info_cat_basic:   '基础统计',
    info_cat_preflop: '翻前',
    info_cat_postflop:'翻后',
    info_cat_math:    '数学',
    info_cat_concept: '核心概念',
  },

  en: {
    nav_train: 'Train',
    nav_stats: 'Stats',
    nav_info:  'Glossary',

    btn_start:   'Start Training',
    btn_end:     'End Session',
    session_active: 'Session #{{id}} active',

    filter_all:     'All',
    filter_preflop: 'Preflop',
    filter_flop:    'Flop',
    filter_turn:    'Turn',
    filter_river:   'River',

    stat_total:    'Decisions',
    stat_correct:  'Correct',
    stat_pct:      'Accuracy',
    stat_sessions: 'Sessions',

    opp_title:        'Opponent type',
    opp_random:       '🎲 Random',
    opp_signal_title: 'Key signals',
    opp_exploit_title:'Exploit tips',
    opp_key_signals:  'Key signals',
    opp_exploit_btn:  'Exploitative analysis',

    your_hand:     'Your hand',
    pot_label:     'Pot',
    stack_label:   'Stack',
    preflop_ctx:   'Action is on you (first to act)',
    postflop_ctx:  'Opponent checks, action on you',

    action_fold:  'Fold',
    action_call:  'Call',
    action_check: 'Check',
    action_raise: 'Raise',
    action_bet:   'Bet',
    action_allin: 'All-in',
    action_3bet:  '3-Bet',
    action_4bet:  '4-Bet',

    correct_prefix:   'Correct!',
    wrong_prefix:     'GTO says:',
    next_btn:         'Next →',
    equity_btn:       'Calculate equity (Monte Carlo)',
    equity_vs:        'vs random range ({{n}} sims)',
    equity_tie:       'Tie: {{n}}%',
    exploit_title:    'Exploitative analysis:',

    round_title:   'Session summary',
    round_pct_lbl: 'correct',
    new_round_btn: 'Start new session',

    tools_title:      'GTO Calculators',
    tool_odds_title:  'Pot Odds',
    tool_ev_title:    'EV Calculator',
    lbl_pot:          'Pot',
    lbl_bet:          'Villain bet',
    lbl_myeq:         'My equity',
    lbl_evbet:        'Bet size',
    lbl_fold_pct:     'Fold %',
    lbl_called_eq:    'Equity when called',
    unit_bb:          'bb',
    unit_pct:         '%',
    unit_eq_opt:      '% (optional)',
    odds_needed:      'Needed equity',
    odds_ratio:       'Pot odds',
    odds_betpct:      'Bet % of pot',
    odds_good:        'Call profitable (+{{n}}%)',
    odds_bad:         'Call unprofitable (−{{n}}%)',
    ev_bet_lbl:       'Bet EV',
    ev_check_lbl:     'Check EV',
    ev_fold_lbl:      'Fold EV',
    ev_best:          'Best action',
    ev_gto_fold:      'GTO fold rate',
    ev_action_bet:    'Bet',
    ev_action_check:  'Check',
    ev_action_fold:   'Fold',

    stats_overall:    'Overall performance',
    stats_by_street:  'Accuracy by street',
    stats_by_pos:     'Accuracy by position',
    stats_weak:       '⚠️ Weak spots (lowest accuracy)',
    stats_recent:     'Recent decisions',
    stats_sessions:   'Session history',
    stats_no_data:    'No data yet',
    stats_no_weak:    'Need at least 3 records to show',
    stats_no_recent:  'No records yet',
    tbl_hand:         'Hand',
    tbl_count:        'Attempts',
    tbl_correct:      'Correct',
    tbl_pct:          'Accuracy',
    tbl_street:       'Street',
    tbl_pos:          'Position',
    tbl_your_action:  'Your action',
    tbl_gto:          'GTO',
    tbl_result:       'Result',
    tbl_session:      'Session',
    tbl_time:         'Time',
    tbl_decisions:    'Decisions',
    result_ok:        'Correct',
    result_no:        'Wrong',

    street_preflop: 'Preflop',
    street_flop:    'Flop',
    street_turn:    'Turn',
    street_river:   'River',

    info_title:       'Glossary',
    info_search:      'Search terms...',
    info_no_results:  'No terms found',
    info_full_name:   'Full name',
    info_definition:  'Definition',
    info_formula:     'Formula',
    info_benchmarks:  'Benchmarks',
    info_example:     'Example',
    info_cat_all:     'All',
    info_cat_basic:   'Basic stats',
    info_cat_preflop: 'Preflop',
    info_cat_postflop:'Postflop',
    info_cat_math:    'Math',
    info_cat_concept: 'Concepts',
  }
};

// helper: t('session_active', {id: 3}) → 'Session #3 active'
function t(key, vars) {
  const lang = window._lang || 'zh';
  let str = (I18N[lang] && I18N[lang][key]) || (I18N['zh'][key]) || key;
  if (vars) Object.entries(vars).forEach(([k,v]) => { str = str.replace('{{'+k+'}}', v); });
  return str;
}

function setGlobalLang(lang) {
  window._lang = lang;
  localStorage.setItem('gto_lang', lang);
  document.querySelectorAll('[data-i18n]').forEach(el => {
    const key = el.getAttribute('data-i18n');
    el.textContent = t(key);
  });
  document.querySelectorAll('[data-i18n-ph]').forEach(el => {
    el.placeholder = t(el.getAttribute('data-i18n-ph'));
  });
  document.querySelectorAll('.lang-btn').forEach(btn => {
    btn.classList.toggle('active', btn.getAttribute('data-lang') === lang);
  });
  if (typeof onLangChange === 'function') onLangChange(lang);
}

function initLang() {
  window._lang = localStorage.getItem('gto_lang') || 'zh';
  setGlobalLang(window._lang);
}
