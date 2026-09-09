import { createRouter, createWebHistory } from 'vue-router';

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/home' },
    { path: '/home', name: 'home', component: () => import('./views/HomeView.vue') },
    { path: '/discover', name: 'discover', component: () => import('./views/DiscoverView.vue') },
    { path: '/ideas', name: 'ideas', component: () => import('./views/IdeasView.vue') },
    { path: '/builds', name: 'builds', component: () => import('./views/BuildsView.vue') },
    { path: '/manage', name: 'manage', component: () => import('./views/ManagementView.vue') },
  ],
  scrollBehavior: () => ({ top: 0 }),
});
