<script setup lang="ts">
import { ref } from 'vue'
import { Heart, MessageCircle, UserCircle, Sparkles, Settings, Key } from 'lucide-vue-next'

const emit = defineEmits<{ close: [] }>()

const currentStep = ref(0)

const steps = [
  {
    icon: Heart,
    title: 'Welcome to Easy Single',
    subtitle: 'An AI companion who chats with you, remembers what you said, and has moods of her own.',
    color: '#FF7DAF',
    items: [
      'You can build your own AI character. She remembers every conversation and her mood shifts with what you talk about.',
      'Do not feel like building one? The home page comes with 3 ready-made characters you can talk to straight away.',
      'Before you start there is one small thing to do: give the AI its "key" (an API key). It is free, or close enough.',
      'No worries — follow the steps below and you will be set up in about 5 minutes.',
    ],
  },
  {
    icon: Key,
    title: 'Step 1: Get an API key',
    subtitle: 'A phone needs credit to make calls; AI needs fuel to run.',
    color: '#FFD4A8',
    items: [
      'Open aistudio.google.com/apikey and sign in with your Google account',
      'Click "Create API key", pick a project (or make a new one), then copy the key it shows you. It only appears once.',
      'There is a free tier with plenty of room to chat. No card needed to get started.',
      'Keep the key somewhere safe — you will paste it into the next step.',
    ],
  },
  {
    icon: Settings,
    title: 'Step 2: Paste the key into the site',
    subtitle: 'This is where the API key you just copied goes.',
    color: '#E8808A',
    items: [
      'Click your avatar in the top right, open "Profile" and scroll to the "API settings" section',
      'API key: paste the key you copied from Google AI Studio',
      'Endpoint: leave it on Default, or use https://generativelanguage.googleapis.com',
      'Model: gemini-1.5-flash is a great default. Hit "Test connection" — a green tick means you are good to go, then save.',
    ],
  },
  {
    icon: Sparkles,
    title: 'Step 3: Create your character',
    subtitle: 'With a key in place, AI can build characters for you.',
    color: '#C4A1FF',
    items: [
      'Describe: say in plain words who you want (e.g. "20, a student, sweet and gentle, loves cooking and anime"). AI writes her full personality, looks and speaking style for you — this one needs an API key.',
      'No key yet? Choose "Skip, I\'ll write it" and fill in the fields yourself. You can still create a character, you just cannot chat yet.',
      'Import a chat log: paste in a real conversation and AI "distils" her speaking style from it (this also needs an API key).',
      'You can upload an avatar while you create her, and swap it later whenever you like.',
    ],
  },
  {
    icon: MessageCircle,
    title: 'Step 4: Start chatting',
    subtitle: 'Just like texting a friend — she is always online.',
    color: '#FF7DAF',
    items: [
      'Tap a character card to open the chat. You can send text, emoji and photos.',
      'Desktop: Enter to send, Shift + Enter for a new line.',
      'Mobile: tap the send button at the end of the input box — the return key just adds a line.',
      'You can recall any message, and if you are not happy with her reply just hit retry and she will say it again.',
    ],
  },
  {
    icon: UserCircle,
    title: 'Other things to try',
    subtitle: 'Take your time, nothing here is urgent.',
    color: '#C4A1FF',
    items: [
      'Edit her persona: tap her avatar in the chat to adjust her looks, personality and speaking style at any point.',
      'Memories: your profile shows what she remembers about you, and you can edit or delete any of it.',
      'Photos: change your own avatar in your profile, and hers in the character editor.',
      'Multiple characters: tap "+" on the home page to make another. Each one keeps her own conversations and memories.',
    ],
  },
]

function next() {
  if (currentStep.value < steps.length - 1) {
    currentStep.value++
  } else {
    localStorage.setItem('guide_read', '1')
    emit('close')
  }
}

function skip() {
  localStorage.setItem('guide_read', '1')
  emit('close')
}
</script>

<template>
  <Teleport to="body">
    <transition name="guide-fade">
      <div class="guide-overlay">
        <div class="guide-modal">
          <!-- Progress dots -->
          <div class="guide-progress">
            <div
              v-for="(s, i) in steps"
              :key="i"
              class="guide-dot"
              :class="{ active: i <= currentStep, done: i < currentStep }"
              :style="i <= currentStep ? { background: s.color } : {}"
            />
          </div>

          <!-- Skip button -->
          <button class="guide-skip" @click="skip">Skip</button>

          <!-- Icon -->
          <div class="guide-icon-wrap" :style="{ background: steps[currentStep].color }">
            <component :is="steps[currentStep].icon" :size="36" color="#fff" />
          </div>

          <!-- Content -->
          <div class="guide-body">
            <h2 class="guide-title">{{ steps[currentStep].title }}</h2>
            <p class="guide-subtitle">{{ steps[currentStep].subtitle }}</p>

            <ul class="guide-list">
              <li v-for="item in steps[currentStep].items" :key="item" class="guide-item">
                {{ item }}
              </li>
            </ul>
          </div>

          <!-- Footer button -->
          <div class="guide-footer">
            <button class="guide-btn" :style="{ background: steps[currentStep].color }" @click="next">
              {{ currentStep < steps.length - 1 ? 'Next' : 'Start chatting' }}
            </button>
          </div>
        </div>
      </div>
    </transition>
  </Teleport>
</template>

<style scoped>
.guide-overlay {
  position: fixed;
  inset: 0;
  z-index: 2000;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(74, 37, 53, 0.4);
  backdrop-filter: blur(4px);
}

.guide-modal {
  background: #fff;
  border-radius: 28px;
  box-shadow: 0 8px 48px rgba(255, 125, 175, 0.18);
  width: 420px;
  max-width: 92vw;
  padding: 36px 32px 28px;
  display: flex;
  flex-direction: column;
  align-items: center;
  position: relative;
}

/* Progress dots */
.guide-progress {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 28px;
}
.guide-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #F5D0DA;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}
.guide-dot.active {
  transform: scale(1.3);
}
.guide-dot.done {
  transform: scale(0.8);
  opacity: 0.5;
}

/* Skip */
.guide-skip {
  position: absolute;
  top: 14px;
  right: 16px;
  font-size: 13px;
  color: #C495A8;
  background: none;
  border: none;
  cursor: pointer;
  font-family: inherit;
  transition: color 0.2s;
}
.guide-skip:hover {
  color: #4A2535;
}

/* Icon */
.guide-icon-wrap {
  width: 80px;
  height: 80px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 24px;
  transition: background 0.3s;
}

/* Body copy */
.guide-body {
  text-align: center;
  width: 100%;
}
.guide-title {
  font-family: var(--font-heading);
  font-size: 20px;
  font-weight: 700;
  color: #4A2535;
  margin-bottom: 6px;
}
.guide-subtitle {
  font-size: 13px;
  color: #C495A8;
  margin-bottom: 20px;
  line-height: 1.6;
}

.guide-list {
  list-style: none;
  padding: 0;
  margin: 0;
  text-align: left;
}
.guide-item {
  position: relative;
  padding: 8px 0 8px 20px;
  font-size: 14px;
  color: #4A2535;
  line-height: 1.7;
}
.guide-item::before {
  content: '';
  position: absolute;
  left: 0;
  top: 14px;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #FFB8D4;
}

/* Button */
.guide-footer {
  margin-top: 24px;
}
.guide-btn {
  padding: 12px 48px;
  border: none;
  border-radius: 9999px;
  color: #fff;
  font-size: 15px;
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
  transition: all 0.25s cubic-bezier(0.34, 1.56, 0.64, 1);
}
.guide-btn:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.12);
}
.guide-btn:active {
  transform: scale(0.97);
}

/* Animation */
.guide-fade-enter-active,
.guide-fade-leave-active {
  transition: opacity 0.25s ease;
}
.guide-fade-enter-from,
.guide-fade-leave-to {
  opacity: 0;
}

@media (max-width: 480px) {
  .guide-modal {
    padding: 24px 18px 20px;
    border-radius: 24px;
  }
  .guide-icon-wrap {
    width: 64px;
    height: 64px;
    margin-bottom: 16px;
  }
  .guide-title {
    font-size: 17px;
  }
  .guide-item {
    font-size: 13px;
    padding: 6px 0 6px 18px;
  }
  .guide-item::before {
    top: 12px;
  }
  .guide-btn {
    padding: 10px 36px;
    font-size: 14px;
  }
}
</style>
