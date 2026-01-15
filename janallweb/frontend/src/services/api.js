import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json'
  }
})

// Request interceptor
api.interceptors.request.use(
  (config) => {
    // İsteğe token eklenebilir
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// Response interceptor
api.interceptors.response.use(
  (response) => {
    return response
  },
  (error) => {
    if (error.response) {
      // Server hatası
      console.error('API Hatası:', error.response.data)
    } else if (error.request) {
      // İstek gönderildi ama yanıt alınamadı
      console.error('Bağlantı hatası:', error.request)
    } else {
      // İstek hazırlanırken hata
      console.error('Hata:', error.message)
    }
    return Promise.reject(error)
  }
)

export default api









