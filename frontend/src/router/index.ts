import { createRouter, createWebHistory } from 'vue-router'
import FeedView from '../views/FeedView.vue'
import ManageView from '../views/ManageView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: FeedView },
    { path: '/manage', component: ManageView },
  ],
})

export default router
