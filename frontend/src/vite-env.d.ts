/// <reference types="vite/client" />

import 'react'

declare module 'react' {
  interface TextareaHTMLAttributes<T> {
    list?: string
  }
}
