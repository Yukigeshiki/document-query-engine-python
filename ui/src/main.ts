/** Application entry point — creates the Vue app, installs plugins, and mounts to the DOM. */
import { createApp } from 'vue'
import '@/assets/index.css'
import App from './App.vue'
import router from '@/router'
import pinia from '@/stores'

const app = createApp(App)

app.use(pinia)
app.use(router)

app.mount('#app')
