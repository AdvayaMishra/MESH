"use client";
import * as React from "react";
import { cn } from "@/lib/utils/cn";

const base =
  "w-full rounded-xl border border-line-strong bg-white px-3.5 text-sm text-ink placeholder:text-ink-3 transition-shadow focus:border-violet focus:outline-none focus:ring-4 focus:ring-violet/15 disabled:bg-[#f4f6fb] disabled:text-ink-3 aria-[invalid=true]:border-coral aria-[invalid=true]:ring-coral/15";

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => <input ref={ref} className={cn(base, "h-11", className)} {...props} />
);
Input.displayName = "Input";

export const Textarea = React.forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement>>(
  ({ className, ...props }, ref) => <textarea ref={ref} className={cn(base, "min-h-24 py-2.5", className)} {...props} />
);
Textarea.displayName = "Textarea";

export const Select = React.forwardRef<HTMLSelectElement, React.SelectHTMLAttributes<HTMLSelectElement>>(
  ({ className, children, ...props }, ref) => (
    <select ref={ref} className={cn(base, "h-11 appearance-none bg-[url('data:image/svg+xml;utf8,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%2216%22 height=%2216%22 viewBox=%220 0 24 24%22 fill=%22none%22 stroke=%22%2394A3B8%22 stroke-width=%222%22 stroke-linecap=%22round%22 stroke-linejoin=%22round%22><path d=%22m6 9 6 6 6-6%22/></svg>')] bg-[length:16px] bg-[right_12px_center] bg-no-repeat pr-9", className)} {...props}>
      {children}
    </select>
  )
);
Select.displayName = "Select";

export function Field({label,hint,error,children,htmlFor}:{label:string;hint?:string;error?:string;children:React.ReactNode;htmlFor?:string}) {
  const generated=React.useId();
  const first=React.Children.toArray(children).find(React.isValidElement);
  const existing=React.isValidElement<{id?:string}>(first)?first.props.id:undefined;
  const identifier=htmlFor??existing??generated;
  const elements=React.Children.toArray(children);
  const linkedIndex=elements.findIndex(child=>React.isValidElement(child)&&(child.type===Input||child.type===Select||child.type===Textarea));
  const controls=elements.map((child,index)=>{
    if(index===linkedIndex&&React.isValidElement<{id?:string;"aria-describedby"?:string;"aria-invalid"?:React.AriaAttributes["aria-invalid"]}>(child)&&(child.type===Input||child.type===Select||child.type===Textarea)){
      return React.cloneElement(child,{id:child.props.id??identifier,"aria-invalid":error?true:child.props["aria-invalid"],"aria-describedby":[child.props["aria-describedby"],(error||hint)&&`${identifier}-description`].filter(Boolean).join(" ")||undefined});
    }
    return child;
  });
  return <div className="space-y-1.5"><label htmlFor={identifier} className="text-[13px] font-medium text-ink">{label}</label>{controls}{error?<p id={`${identifier}-description`} role="alert" className="text-xs text-[#d6294f]">{error}</p>:hint?<p id={`${identifier}-description`} className="text-xs text-ink-3">{hint}</p>:null}</div>;
}
