<template>
  <section class="page" data-module="client2-detail">
    <header class="page-head">
      <div>
        <h2>委托方详情</h2>
        <p class="page-desc">接单结论与档案列表、下单校验同源，均来自后端唯一评估口径。</p>
      </div>
      <div class="page-actions">
        <RouterLink class="btn" type="button" to="/client2">返回列表</RouterLink>
      </div>
    </header>

    <p v-if="errorMessage" class="error-text">{{ errorMessage }}</p>

    <article v-if="detail" class="detail-card">
      <div class="decision-row">
        <span class="decision-label">接单结论</span>
        <strong :class="decisionClass(detail['接单结论'])">{{ detail['接单结论'] }}</strong>
        <span class="decision-reason">{{ detail['判定原因'] }}</span>
      </div>
      <dl class="detail-grid">
        <div v-for="field in fields" :key="field" class="detail-item">
          <dt>{{ field }}</dt>
          <dd>{{ detail[field] ?? '—' }}</dd>
        </div>
      </dl>
    </article>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import { request } from '@/api/client'

type Detail = Record<string, string | number | boolean | null>

const route = useRoute()
const detail = ref<Detail | null>(null)
const errorMessage = ref('')

// 只展示后端返回的字段；企业类别/信用等级/合同期限如何推出结论，前端不重复实现。
const fields = [
  '委托方编号', '委托方名称', '企业类别', '信用等级',
  '签约日期', '合同期限', '对接联系人', '委托方状态',
]

function decisionClass(decision: unknown): string {
  if (decision === '可接单') return 'tag tag-ok'
  if (decision === '暂缓接单') return 'tag tag-hold'
  return 'tag tag-block'
}

async function reload() {
  errorMessage.value = ''
  try {
    const response = await request(`/api/client2/${String(route.params.id)}`)
    if (!response.ok) {
      throw new Error('委托方详情读取失败')
    }
    detail.value = await response.json()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '委托方详情读取失败'
  }
}

onMounted(reload)
</script>
