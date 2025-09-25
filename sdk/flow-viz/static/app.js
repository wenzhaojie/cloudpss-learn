async function runPowerFlow(rid) {
  const status = document.getElementById('status');
  status.textContent = '⏳ 提交任务中...';
  try {
    const resp = await fetch('/api/powerflow?rid=' + encodeURIComponent(rid));
    if (!resp.ok) {
      status.textContent = '❌ 请求失败：' + resp.status + ' ' + resp.statusText;
      return;
    }
    const data = await resp.json();
    if (data.error) {
      status.textContent = '❌ ' + data.error;
      return;
    }
    status.textContent = (data.logs && data.logs.length)
      ? data.logs.map(l => `[${l.level}] ${l.content}`).join('\n')
      : '✅ 任务完成。';

    renderTable('buses', data.buses.headers, data.buses.rows);
    renderTable('branches', data.branches.headers, data.branches.rows);
  } catch (e) {
    status.textContent = '❌ 异常：' + e.message;
  }
}

function renderTable(id, headers, rows) {
  const table = document.getElementById(id);
  if (!headers || !headers.length) {
    table.innerHTML = '<tbody><tr><td>无数据</td></tr></tbody>';
    return;
  }
  const thead = '<thead><tr>' + headers.map(h => `<th>${h}</th>`).join('') + '</tr></thead>';
  const tbody = '<tbody>' + rows.map(r => {
    return '<tr>' + headers.map(h => `<td>${r[h] ?? ''}</td>`).join('') + '</tr>';
  }).join('') + '</tbody>';
  table.innerHTML = thead + tbody;
}

// 表单：手动触发计算
document.getElementById('pfForm').addEventListener('submit', (e) => {
  e.preventDefault();
  const rid = e.target.rid.value || 'model/CloudPSS/IEEE3';
  runPowerFlow(rid);
});

// CSV 下载：点击时直接请求后端导出接口（不再自动运行）
document.getElementById('dlBuses').addEventListener('click', () => {
  const rid = document.querySelector('input[name="rid"]').value || 'model/CloudPSS/IEEE3';
  const url = '/api/export/csv?table=buses&rid=' + encodeURIComponent(rid);
  window.open(url, '_blank');
});
document.getElementById('dlBranches').addEventListener('click', () => {
  const rid = document.querySelector('input[name="rid"]').value || 'model/CloudPSS/IEEE3';
  const url = '/api/export/csv?table=branches&rid=' + encodeURIComponent(rid);
  window.open(url, '_blank');
});

// 注意：不再在页面加载时自动调用 runPowerFlow()
// 这样就不会“一启动 Python 就自动去计算了”
