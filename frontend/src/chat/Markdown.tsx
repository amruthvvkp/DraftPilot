import ReactMarkdown, { type Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Link } from 'react-router'

const components: Components = {
  a: ({ href, children }) => href && href.startsWith('/') && !href.startsWith('//')
    ? <Link to={href}>{children}</Link>
    : <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>,
}

/** Assistant text as Markdown (GitHub flavour). Raw HTML is never rendered. */
export default function Markdown({ text }: { text: string }) {
  return <div className="chat-markdown"><ReactMarkdown remarkPlugins={[remarkGfm]} skipHtml components={components}>{text}</ReactMarkdown></div>
}
