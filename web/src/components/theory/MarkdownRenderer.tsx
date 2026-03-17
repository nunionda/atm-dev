import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
import { slugify } from '../../lib/tocUtils';
import type { Components } from 'react-markdown';
import './MarkdownRenderer.css';

interface MarkdownRendererProps {
  content: string;
}

const components: Components = {
  h1: ({ children, ...props }) => {
    const text = String(children);
    return <h1 id={slugify(text)} {...props}>{children}</h1>;
  },
  h2: ({ children, ...props }) => {
    const text = String(children);
    return <h2 id={slugify(text)} {...props}>{children}</h2>;
  },
  h3: ({ children, ...props }) => {
    const text = String(children);
    return <h3 id={slugify(text)} {...props}>{children}</h3>;
  },
  h4: ({ children, ...props }) => {
    const text = String(children);
    return <h4 id={slugify(text)} {...props}>{children}</h4>;
  },
};

export function MarkdownRenderer({ content }: MarkdownRendererProps) {
  return (
    <div className="markdown-body">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeHighlight]}
        components={components}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
