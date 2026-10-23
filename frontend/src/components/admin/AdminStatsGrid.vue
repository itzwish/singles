<script setup lang="ts">
import { ref } from 'vue'
import { Users, Crown, MessageCircle, Zap, Sparkles, TrendingUp, Activity } from 'lucide-vue-next'
import AdminStatsCard from './AdminStatsCard.vue'

defineProps<{
  displayStats: Record<string, number>
  stats: Record<string, number>
  trend: { date: string; label: string; count: number }[]
  trendMax: number
}>()

const hoveredBar = ref<number | null>(null)
</script>

<template>
  <div class="stats-grid">
    <AdminStatsCard
      :icon="Users" label="Total users"
      :value="displayStats.total_users"
      :subtitle="String(displayStats.today_users || 0)"
    />
    <AdminStatsCard
      :icon="Crown" label="VIP members"
      :value="displayStats.vip_users"
      :subtitle="displayStats.total_users > 0 ? Math.round(displayStats.vip_users / displayStats.total_users * 100) + '% of users' : ''"
    />
    <AdminStatsCard
      :icon="MessageCircle" label="Total messages"
      :value="displayStats.total_messages"
      :subtitle="displayStats.total_conversations + ' conversations'"
    />
    <AdminStatsCard
      :icon="Zap" label="Messages today"
      :value="displayStats.today_messages"
      :subtitle="displayStats.active_users_today + ' active'"
    />
    <AdminStatsCard
      :icon="Sparkles" label="Characters"
      :value="displayStats.total_characters"
      subtitle="AI companions"
    />
  </div>

  <div class="middle-row">
    <div class="panel chart-panel">
      <div class="panel-header">
        <TrendingUp :size="18" class="panel-icon" />
        <h3 class="panel-title">Messages, last 7 days</h3>
      </div>
      <div class="chart-body">
        <svg class="chart-svg" viewBox="0 0 600 200" preserveAspectRatio="xMidYMid meet">
          <line v-for="i in 4" :key="'gl'+i"
            :x1="60" :x2="580" :y1="20 + (i-1) * 40" :y2="20 + (i-1) * 40"
            stroke="var(--color-border)" stroke-width="1" stroke-dasharray="4,4" opacity="0.4"
          />
          <text v-for="i in 5" :key="'yl'+i"
            :x="52" :y="23 + (4-i) * 40"
            text-anchor="end" font-size="11" fill="var(--color-text-muted)"
          >{{ Math.round(trendMax * (5-i) / 4) }}</text>
          <g v-for="(d, i) in trend" :key="d.date">
            <rect
              :x="72 + i * 76"
              :y="180 - (d.count / trendMax) * 160"
              width="44" :height="(d.count / trendMax) * 160"
              rx="6"
              fill="var(--color-primary)"
              @mouseenter="hoveredBar = i"
              @mouseleave="hoveredBar = null"
              style="cursor: pointer; transition: fill 0.2s;"
            />
            <text
              v-if="hoveredBar === i"
              :x="72 + i * 76 + 22" :y="176 - (d.count / trendMax) * 160"
              text-anchor="middle" font-size="12" font-weight="700"
              fill="var(--color-primary)"
            >{{ d.count }}</text>
            <text
              :x="72 + i * 76 + 22" y="195"
              text-anchor="middle" font-size="11"
              fill="var(--color-text-muted)"
            >{{ d.label }}</text>
          </g>
          <defs>
            <linearGradient id="barGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stop-color="var(--color-primary)" />
              <stop offset="100%" stop-color="var(--color-primary)20" />
            </linearGradient>
          </defs>
        </svg>
      </div>
    </div>

    <div class="panel info-panel">
      <div class="panel-header">
        <Activity :size="18" class="panel-icon" />
        <h3 class="panel-title">Overview</h3>
      </div>
      <div class="info-list">
        <div class="info-item">
          <span class="info-dot active" />
          <div>
            <span class="info-val">{{ displayStats.active_users_today }}</span>
            <span class="info-hint">Active today</span>
          </div>
        </div>
        <div class="info-item">
          <span class="info-dot new" />
          <div>
            <span class="info-val">{{ displayStats.today_users }}</span>
            <span class="info-hint">New signups today</span>
          </div>
        </div>
        <div class="info-item">
          <span class="info-dot" />
          <div>
            <span class="info-val">{{ displayStats.total_conversations }}</span>
            <span class="info-hint">Total conversations</span>
          </div>
        </div>
        <div class="info-item">
          <span class="info-dot" />
          <div>
            <span class="info-val">{{ displayStats.total_messages / displayStats.total_users > 0 ? (displayStats.total_messages / displayStats.total_users).toFixed(1) : '0' }}</span>
            <span class="info-hint">Messages per user</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.stats-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 16px;
  margin-bottom: 20px;
}

.middle-row {
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: 16px;
  margin-bottom: 20px;
}

.panel {
  background: var(--color-surface);
  border-radius: 16px;
  border: 1px solid var(--color-border);
  overflow: hidden;
}

.panel-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 16px 20px;
  border-bottom: 1px solid var(--color-border);
}

.panel-icon { color: var(--color-primary); flex-shrink: 0; }

.panel-title {
  font-family: var(--font-heading);
  font-size: 15px;
  font-weight: 700;
  color: var(--color-text);
}

.chart-body { padding: 20px 24px 12px; }
.chart-svg { width: 100%; height: 220px; }

.info-list { padding: 8px 0; }

.info-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 20px;
  transition: background 0.15s;
}
.info-item:hover { background: var(--color-sakura-light); }

.info-dot {
  width: 10px; height: 10px;
  border-radius: 50%;
  background: var(--color-border-strong);
  flex-shrink: 0;
}
.info-dot.active { background: var(--color-primary); box-shadow: 0 0 6px var(--color-primary)60; }
.info-dot.new { background: var(--color-primary); box-shadow: 0 0 6px var(--color-primary)60; }

.info-val {
  font-family: var(--font-heading);
  font-size: 20px;
  font-weight: 700;
  color: var(--color-text);
}

.info-hint {
  font-size: 12px;
  color: var(--color-text-muted);
  display: block;
  margin-top: 1px;
}

@media (max-width: 1200px) {
  .stats-grid { grid-template-columns: repeat(3, 1fr); }
  .middle-row { grid-template-columns: 1fr; }
}

@media (max-width: 768px) {
  .stats-grid { grid-template-columns: repeat(2, 1fr); gap: 10px; }
}
</style>
