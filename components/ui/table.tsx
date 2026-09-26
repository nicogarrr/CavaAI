"use client"

import * as React from "react"

import { cn } from "@/lib/utils"

// "use client" es OBLIGATORIA: el contexto de densidad (React.createContext a
// nivel de modulo) no existe en el grafo de Server Components - sin la
// directiva, cualquier pagina server que importe Table rompe el build en
// "collect page data" (createContext is not a function en /watchlist).

/**
 * Densidad de la tabla. Las cabeceras escritas a mano usan `py-2 px-3` y las
 * que salen de este modulo usan `h-12 px-4`; convivir con las dos densidades a
 * la vez descuadraba la rejilla. `dense` se hereda por contexto para que basta
 * con `<Table dense>` (o `<TableRow dense>`) y no repetirlo en cada celda.
 */
const TableDensityContext = React.createContext(false)

/** `undefined` = hereda del padre; `true`/`false` = fuerza la densidad. */
function useTableDensity(override?: boolean): boolean {
  const inherited = React.useContext(TableDensityContext)
  return override ?? inherited
}

type TableProps = React.HTMLAttributes<HTMLTableElement> & {
  dense?: boolean
  /**
   * Nombre accesible de la region con scroll horizontal. Con teclado no hay
   * barra de scroll, asi que sin `tabIndex` el contenido ancho queda
   * inalcanzable (WCAG 2.1.1). Solo debe pasarse cuando la tabla puede
   * desbordar de verdad: un `tabIndex` en un contenedor quieto crea un stop de
   * tabulacion inutil.
   */
  regionLabel?: string
}

const Table = React.forwardRef<HTMLTableElement, TableProps>(
  ({ className, dense = false, regionLabel, ...props }, ref) => (
    // `overflow-x-auto` y no `overflow-auto`: con `auto` en ambos ejes el
    // contenedorellia el scroll vertical de la pagina al hacer scroll sobre la
    // tabla, y `min-w-0` evita que la tabla ensanche un contenedor flex.
    <div
      className="relative w-full min-w-0 overflow-x-auto"
      {...(regionLabel
        ? { role: "region", "aria-label": regionLabel, tabIndex: 0 }
        : null)}
    >
      <TableDensityContext.Provider value={dense}>
        <table
          ref={ref}
          className={cn("w-full caption-bottom text-sm", className)}
          {...props}
        />
      </TableDensityContext.Provider>
    </div>
  ),
)
Table.displayName = "Table"

const TableHeader = React.forwardRef<
  HTMLTableSectionElement,
  React.HTMLAttributes<HTMLTableSectionElement>
>(({ className, ...props }, ref) => (
  <thead ref={ref} className={cn("[&_tr]:border-b", className)} {...props} />
))
TableHeader.displayName = "TableHeader"

const TableBody = React.forwardRef<
  HTMLTableSectionElement,
  React.HTMLAttributes<HTMLTableSectionElement>
>(({ className, ...props }, ref) => (
  <tbody
    ref={ref}
    className={cn("[&_tr:last-child]:border-0", className)}
    {...props}
  />
))
TableBody.displayName = "TableBody"

const TableFooter = React.forwardRef<
  HTMLTableSectionElement,
  React.HTMLAttributes<HTMLTableSectionElement>
>(({ className, ...props }, ref) => (
  <tfoot
    ref={ref}
    className={cn(
      "border-t bg-muted/50 font-medium [&>tr]:last:border-b-0",
      className
    )}
    {...props}
  />
))
TableFooter.displayName = "TableFooter"

const TableRow = React.forwardRef<
  HTMLTableRowElement,
  React.HTMLAttributes<HTMLTableRowElement> & { dense?: boolean }
>(({ className, dense, ...props }, ref) => {
  const resolved = useTableDensity(dense)
  return (
    <TableDensityContext.Provider value={resolved}>
      <tr
        ref={ref}
        className={cn(
          "border-b border-gray-700/50 transition-all duration-150 hover:bg-gray-700/30 data-[state=selected]:bg-gray-700/50",
          className
        )}
        {...props}
      />
    </TableDensityContext.Provider>
  )
})
TableRow.displayName = "TableRow"

const TableHead = React.forwardRef<
  HTMLTableCellElement,
  React.ThHTMLAttributes<HTMLTableCellElement> & {
    dense?: boolean
    /** `col` por defecto: sin esto ningun lector de pantalla anuncia las
     *  cabeceras. Se puede pasar `row` si el `th` rotula la fila. */
    scope?: React.ThHTMLAttributes<HTMLTableCellElement>["scope"]
  }
>(({ className, dense, scope = "col", ...props }, ref) => {
  const resolved = useTableDensity(dense)
  return (
    <th
      ref={ref}
      scope={scope}
      className={cn(
        resolved
          ? "px-3 py-2 text-left align-middle font-medium text-muted-foreground [&:has([role=checkbox])]:pr-0"
          : "h-12 px-4 text-left align-middle font-medium text-muted-foreground [&:has([role=checkbox])]:pr-0",
        className
      )}
      {...props}
    />
  )
})
TableHead.displayName = "TableHead"

const TableCell = React.forwardRef<
  HTMLTableCellElement,
  React.TdHTMLAttributes<HTMLTableCellElement> & { dense?: boolean }
>(({ className, dense, ...props }, ref) => {
  const resolved = useTableDensity(dense)
  return (
    <td
      ref={ref}
      className={cn(
        resolved
          ? "px-3 py-2 align-middle [&:has([role=checkbox])]:pr-0"
          : "p-4 align-middle [&:has([role=checkbox])]:pr-0",
        className
      )}
      {...props}
    />
  )
})
TableCell.displayName = "TableCell"

/** Se apila en el DOM (`<caption>` es el primero de `<table>`): da nombre a la
 *  tabla en el modo lectura y es el destino de `aria-describedby`. Pasar
 *  `className="sr-only"` cuando el titulo visible ya esta en el `<h2>`. */
const TableCaption = React.forwardRef<
  HTMLTableCaptionElement,
  React.HTMLAttributes<HTMLTableCaptionElement>
>(({ className, ...props }, ref) => (
  <caption
    ref={ref}
    className={cn("mt-4 text-sm text-muted-foreground", className)}
    {...props}
  />
))
TableCaption.displayName = "TableCaption"

export {
  Table,
  TableHeader,
  TableBody,
  TableFooter,
  TableHead,
  TableRow,
  TableCell,
  TableCaption,
}
