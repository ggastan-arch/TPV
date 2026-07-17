"""Catalogo de ejemplo para la BD demo (`tpv_demo.db`).

Reconstruccion de un arbol de familias real de una tienda de acuariofilia de
agua dulce (se ha excluido a proposito todo lo de acuario marino). Los precios
son PVP orientativos con IVA incluido, ajustados a valores de venta minorista
actuales (los importes del historico original NO se reutilizan).

Tipos de IVA segun las reglas de negocio de CLAUDE.md, no segun el historico:
peces 21 %, plantas vivas ornamentales 10 %, alimentacion animal 21 %,
complementos 21 %.

Datos puramente de demostracion: no representan stock ni precios reales.
"""
from __future__ import annotations

# Arbol de familias (agua dulce). El separador "/" marca la jerarquia; los
# padres se crean automaticamente aunque no aparezcan sueltos. El orden de la
# lista fija el campo `orden` dentro de cada nivel.
FAMILIAS: list[str] = [
    "Peces por familias",
    "Peces por familias/Vivíparos",
    "Peces por familias/Carácidos",
    "Peces por familias/Cíclidos",
    "Peces por familias/Cíclidos africanos",
    "Peces por familias/Discos",
    "Peces por familias/Anabántidos",
    "Peces por familias/Peces de fondo",
    "Peces por familias/Killis",
    "Peces por familias/Otras familias",
    "Agua fría",
    "Agua fría/Peces de agua fría",
    "Plantas",
    "Alimento",
    "Alimento/Alimento seco",
    "Alimento/Alimento congelado",
    "Alimento/Alimento agua fría",
    "Tratamiento del agua",
    "Tratamiento del agua/Acondicionadores",
    "Tratamiento del agua/Abonos",
    "Tratamiento del agua/Bacterias",
    "Tratamiento del agua/Correctores",
    "Tratamiento del agua/Tests de agua",
    "Medicamentos",
    "Filtración",
    "Filtración/Filtros",
    "Filtración/Materiales filtrantes",
    "Filtración/Recambios",
    "Iluminación",
    "Iluminación/Equipos LED",
    "Iluminación/Fluorescentes",
    "Iluminación/Pantallas",
    "Calentadores",
    "Aireadores",
    "Comederos",
    "Decoración",
    "Decoración/Gravas y sustratos",
    "Decoración/Maderas",
    "Decoración/Rocas",
    "Decoración/Artificiales",
    "Decoración/Fondos",
    "Acuarios",
    "Acuarios/Kits",
    "Acuarios/Urnas de cristal",
    "Accesorios",
]

# Familias (rutas completas) OCULTAS en la navegacion tactil por defecto: material
# con codigo de barras que satura la pantalla y se vende por escaner/buscador, no
# tocando botones. Ocultar el nodo raiz basta para sacar todo su subarbol del
# drill-down. NO afecta a la venta (los articulos siguen accesibles por EAN/nombre)
# ni a botones explicitos (el seed de la botonera demo tampoco les pone boton).
FAMILIAS_OCULTAS_TACTIL: set[str] = {
    "Alimento",
    "Tratamiento del agua",
    "Medicamentos",
    "Filtración",
    "Iluminación",
    "Calentadores",
    "Aireadores",
    "Comederos",
    "Decoración",
    "Acuarios",
    "Accesorios",
}

# Foto representativa por familia (ruta completa -> /media-demo/...): la de un
# articulo tipico de la familia, para que el boton de familia tambien luzca foto.
# Solo se ponen a las familias VISIBLES en tactil (el material no se navega).
FAMILIAS_IMAGEN_TACTIL: dict[str, str] = {
    "Peces por familias": "/media-demo/disco.jpg",
    "Peces por familias/Vivíparos": "/media-demo/guppy.jpg",
    "Peces por familias/Carácidos": "/media-demo/neon-cardenal.jpg",
    "Peces por familias/Cíclidos": "/media-demo/apistogramma.jpg",
    "Peces por familias/Cíclidos africanos": "/media-demo/lamprologus.jpg",
    "Peces por familias/Discos": "/media-demo/disco.jpg",
    "Peces por familias/Anabántidos": "/media-demo/betta-macho.jpg",
    "Peces por familias/Peces de fondo": "/media-demo/ancistrus.jpg",
    "Peces por familias/Killis": "/media-demo/aphyosemion-australe.jpg",
    "Peces por familias/Otras familias": "/media-demo/balantiocheilus.jpg",
    "Plantas": "/media-demo/anubias.jpg",
    "Agua fría": "/media-demo/carpa-roja.jpg",
    "Agua fría/Peces de agua fría": "/media-demo/carpa-roja.jpg",
}

# Cada articulo: (nombre, nombre_corto, familia, iva, pvp, flags, ean)
#   iva:    "general" (21 %) | "reducido" (10 %)
#   flags:  claves opcionales -> control_stock, precio_libre, requiere_cites
#   ean:    codigo de barras principal (str) o None (peces/plantas a granel)
#
# PVP con IVA incluido, en euros (str -> Decimal). Valores de demostracion.
ARTICULOS: list[dict] = [
    # --- Peces / Vivíparos -------------------------------------------------
    dict(nombre="Guppy macho colores surtidos", corto="Guppy macho",
         familia="Peces por familias/Vivíparos", iva="general", pvp="2.95",
         flags=("control_stock",), imagen="/media-demo/guppy.jpg"),
    dict(nombre="Guppy Delta variado", corto="Guppy delta",
         familia="Peces por familias/Vivíparos", iva="general", pvp="3.10",
         flags=("control_stock",), imagen="/media-demo/guppy-delta.jpg"),
    dict(nombre="Platy rojo", corto="Platy rojo",
         familia="Peces por familias/Vivíparos", iva="general", pvp="2.75",
         flags=("control_stock",)),
    dict(nombre="Molly negro", corto="Molly negro",
         familia="Peces por familias/Vivíparos", iva="general", pvp="3.20",
         flags=("control_stock",)),
    dict(nombre="Xiphophorus helleri (espada) rojo", corto="Espada rojo",
         familia="Peces por familias/Vivíparos", iva="general", pvp="3.50",
         flags=("control_stock",)),
    # --- Peces / Carácidos -------------------------------------------------
    dict(nombre="Neón innesi", corto="Neón",
         familia="Peces por familias/Carácidos", iva="general", pvp="2.10",
         flags=("control_stock",)),
    dict(nombre="Neón cardenal (Paracheirodon axelrodi)", corto="Neón cardenal",
         familia="Peces por familias/Carácidos", iva="general", pvp="3.40",
         flags=("control_stock",), imagen="/media-demo/neon-cardenal.jpg"),
    dict(nombre="Tetra limón (Hyphessobrycon pulchripinnis)", corto="Tetra limón",
         familia="Peces por familias/Carácidos", iva="general", pvp="2.60",
         flags=("control_stock",)),
    dict(nombre="Pez hacha mármol", corto="Hacha mármol",
         familia="Peces por familias/Carácidos", iva="general", pvp="4.90",
         flags=("control_stock",)),
    # --- Peces / Cíclidos --------------------------------------------------
    dict(nombre="Escalar velo (Pterophyllum scalare)", corto="Escalar velo",
         familia="Peces por familias/Cíclidos", iva="general", pvp="8.50",
         flags=("control_stock",)),
    dict(nombre="Ramirezi eléctrico azul", corto="Ramirezi azul",
         familia="Peces por familias/Cíclidos", iva="general", pvp="9.90",
         flags=("control_stock",)),
    dict(nombre="Apistogramma borellii", corto="Apisto. borellii",
         familia="Peces por familias/Cíclidos", iva="general", pvp="11.50",
         flags=("control_stock",), imagen="/media-demo/apistogramma.jpg"),
    # --- Peces / Cíclidos africanos ---------------------------------------
    dict(nombre="Pseudotropheus zebra (Malawi)", corto="Ps. zebra",
         familia="Peces por familias/Cíclidos africanos", iva="general", pvp="7.50",
         flags=("control_stock",)),
    dict(nombre="Labidochromis caeruleus (yellow)", corto="Yellow",
         familia="Peces por familias/Cíclidos africanos", iva="general", pvp="8.20",
         flags=("control_stock",), imagen="/media-demo/lamprologus.jpg"),
    # --- Peces / Discos ----------------------------------------------------
    dict(nombre="Disco Turquesa 8 cm", corto="Disco turquesa",
         familia="Peces por familias/Discos", iva="general", pvp="49.00",
         flags=("control_stock", "precio_libre"), imagen="/media-demo/disco.jpg"),
    dict(nombre="Disco Pigeon Blood 10 cm", corto="Disco pigeon",
         familia="Peces por familias/Discos", iva="general", pvp="69.00",
         flags=("control_stock", "precio_libre")),
    # --- Peces / Anabántidos ----------------------------------------------
    dict(nombre="Betta splendens macho corona", corto="Betta macho",
         familia="Peces por familias/Anabántidos", iva="general", pvp="8.90",
         flags=("control_stock",), imagen="/media-demo/betta-macho.jpg"),
    dict(nombre="Gurami perla (Trichopodus leerii)", corto="Gurami perla",
         familia="Peces por familias/Anabántidos", iva="general", pvp="6.50",
         flags=("control_stock",)),
    # --- Peces / Peces de fondo -------------------------------------------
    dict(nombre="Corydora paleatus", corto="Corydora",
         familia="Peces por familias/Peces de fondo", iva="general", pvp="4.50",
         flags=("control_stock",)),
    dict(nombre="Ancistrus común 5-6 cm", corto="Ancistrus",
         familia="Peces por familias/Peces de fondo", iva="general", pvp="6.90",
         flags=("control_stock",), imagen="/media-demo/ancistrus.jpg"),
    dict(nombre="Botia payaso (Chromobotia macracanthus)", corto="Botia payaso",
         familia="Peces por familias/Peces de fondo", iva="general", pvp="9.50",
         flags=("control_stock",)),
    # --- Peces / Otras familias (con CITES de ejemplo) --------------------
    dict(nombre="Raya motoro (Potamotrygon motoro)", corto="Raya motoro",
         familia="Peces por familias/Otras familias", iva="general", pvp="180.00",
         flags=("control_stock", "precio_libre", "requiere_cites")),
    dict(nombre="Pez globo enano (Carinotetraodon travancoricus)", corto="Globo enano",
         familia="Peces por familias/Otras familias", iva="general", pvp="5.90",
         flags=("control_stock",)),
    dict(nombre="Tiburón bala (Balantiocheilos melanopterus)", corto="Tiburón bala",
         familia="Peces por familias/Otras familias", iva="general", pvp="9.90",
         flags=("control_stock",), imagen="/media-demo/balantiocheilus.jpg"),
    # --- Peces / Killis ----------------------------------------------------
    dict(nombre="Aphyosemion australe (killi cola de lira)", corto="Aphyosemion",
         familia="Peces por familias/Killis", iva="general", pvp="7.50",
         flags=("control_stock",), imagen="/media-demo/aphyosemion-australe.jpg"),
    # --- Agua fría ---------------------------------------------------------
    dict(nombre="Carpín cometa rojo 5-6 cm", corto="Cometa rojo",
         familia="Agua fría/Peces de agua fría", iva="general", pvp="2.50",
         flags=("control_stock",)),
    dict(nombre="Cometa 6-7 cm", corto="Cometa",
         familia="Agua fría/Peces de agua fría", iva="general", pvp="7.90",
         flags=("control_stock",), imagen="/media-demo/carpa-roja.jpg"),
    # --- Plantas (IVA reducido 10 %) --------------------------------------
    dict(nombre="Anubias barteri", corto="Anubias",
         familia="Plantas", iva="reducido", pvp="6.90", flags=("control_stock",),
         imagen="/media-demo/anubias.jpg"),
    dict(nombre="Echinodorus bleheri", corto="Echinodorus",
         familia="Plantas", iva="reducido", pvp="5.50", flags=("control_stock",)),
    dict(nombre="Vallisneria spiralis", corto="Vallisneria",
         familia="Plantas", iva="reducido", pvp="3.50", flags=("control_stock",)),
    dict(nombre="Microsorum pteropus (helecho de Java)", corto="Helecho Java",
         familia="Plantas", iva="reducido", pvp="6.50", flags=("control_stock",)),
    dict(nombre="Cladophora (bola de musgo)", corto="Cladophora",
         familia="Plantas", iva="reducido", pvp="4.90", flags=("control_stock",)),
    # --- Alimento seco -----------------------------------------------------
    dict(nombre="Tropical Supervit escamas 100 ml", corto="Supervit 100",
         familia="Alimento/Alimento seco", iva="general", pvp="5.25",
         flags=("control_stock",), ean="5900469010204"),
    dict(nombre="Tropical Green Algae Wafers 100 ml", corto="Algae Wafers",
         familia="Alimento/Alimento seco", iva="general", pvp="7.50",
         flags=("control_stock",)),
    dict(nombre="JBL NovoBel escamas 250 ml", corto="NovoBel 250",
         familia="Alimento/Alimento seco", iva="general", pvp="9.95",
         flags=("control_stock",)),
    # --- Alimento congelado -----------------------------------------------
    dict(nombre="Larva roja congelada blíster 100 g", corto="Larva roja",
         familia="Alimento/Alimento congelado", iva="general", pvp="3.90",
         flags=("control_stock",)),
    # --- Alimento agua fría -----------------------------------------------
    dict(nombre="Sticks estanque 1 L", corto="Sticks estanque",
         familia="Alimento/Alimento agua fría", iva="general", pvp="6.50",
         flags=("control_stock",)),
    # --- Tratamiento del agua / Acondicionadores --------------------------
    dict(nombre="Fluval Nutrafin acondicionador 120 ml", corto="Acondic. 120",
         familia="Tratamiento del agua/Acondicionadores", iva="general", pvp="7.95",
         flags=("control_stock",), ean="0015561183420"),
    dict(nombre="JBL Biotopol 250 ml", corto="Biotopol 250",
         familia="Tratamiento del agua/Acondicionadores", iva="general", pvp="12.50",
         flags=("control_stock",)),
    # --- Tratamiento del agua / Abonos ------------------------------------
    dict(nombre="JBL Ferropol 250 ml abono líquido", corto="Ferropol 250",
         familia="Tratamiento del agua/Abonos", iva="general", pvp="11.90",
         flags=("control_stock",)),
    dict(nombre="JBL Ferrotabs pastillas (30 ud)", corto="Ferrotabs",
         familia="Tratamiento del agua/Abonos", iva="general", pvp="9.40",
         flags=("control_stock",), ean="4014162012388"),
    dict(nombre="JBL ProFlora bio bolas larga duración (7 ud)", corto="ProFlora 7",
         familia="Tratamiento del agua/Abonos", iva="general", pvp="6.20",
         flags=("control_stock",), ean="4014162010193"),
    # --- Tratamiento del agua / Bacterias ---------------------------------
    dict(nombre="JBL Denitrol 100 ml bacterias", corto="Denitrol 100",
         familia="Tratamiento del agua/Bacterias", iva="general", pvp="8.90",
         flags=("control_stock",)),
    # --- Tratamiento del agua / Correctores -------------------------------
    dict(nombre="JBL pH-Minus 250 ml", corto="pH-Minus",
         familia="Tratamiento del agua/Correctores", iva="general", pvp="8.50",
         flags=("control_stock",)),
    # --- Tratamiento del agua / Tests de agua -----------------------------
    dict(nombre="JBL Test pH 6,0-7,6", corto="Test pH",
         familia="Tratamiento del agua/Tests de agua", iva="general", pvp="10.50",
         flags=("control_stock",), ean="4014162253460"),
    dict(nombre="JBL Easy Test 6 en 1 (50 tiras)", corto="Test 6en1",
         familia="Tratamiento del agua/Tests de agua", iva="general", pvp="14.90",
         flags=("control_stock",)),
    # --- Medicamentos ------------------------------------------------------
    dict(nombre="JBL Punktol Plus 250 (punto blanco)", corto="Punktol",
         familia="Medicamentos", iva="general", pvp="13.50",
         flags=("control_stock",)),
    dict(nombre="Sera Baktopur 50 ml", corto="Baktopur",
         familia="Medicamentos", iva="general", pvp="9.90",
         flags=("control_stock",)),
    # --- Filtración / Filtros ---------------------------------------------
    dict(nombre="Eheim Experience 350 filtro exterior", corto="Eheim 350",
         familia="Filtración/Filtros", iva="general", pvp="149.95",
         flags=("control_stock",), ean="4011708240717"),
    dict(nombre="Eheim miniUP filtro interior nano", corto="Eheim miniUP",
         familia="Filtración/Filtros", iva="general", pvp="24.95",
         flags=("control_stock",)),
    # --- Filtración / Materiales filtrantes -------------------------------
    dict(nombre="JBL MicroMec bolas cerámicas 650 g", corto="MicroMec",
         familia="Filtración/Materiales filtrantes", iva="general", pvp="17.50",
         flags=("control_stock",), ean="4014162625489"),
    dict(nombre="JBL Carbomec ultra carbón activo 400 g", corto="Carbomec",
         familia="Filtración/Materiales filtrantes", iva="general", pvp="12.90",
         flags=("control_stock",), ean="4014162623553"),
    # --- Filtración / Recambios -------------------------------------------
    dict(nombre="Esponja filtrante recambio (2 ud)", corto="Esponja recambio",
         familia="Filtración/Recambios", iva="general", pvp="6.50",
         flags=("control_stock",)),
    # --- Iluminación / Equipos LED ----------------------------------------
    dict(nombre="Pantalla LED sumergible 80 cm agua dulce", corto="LED 80cm",
         familia="Iluminación/Equipos LED", iva="general", pvp="39.90",
         flags=("control_stock",)),
    # --- Iluminación / Fluorescentes --------------------------------------
    dict(nombre="Tubo fluorescente T8 30 W blanco", corto="Tubo T8 30W",
         familia="Iluminación/Fluorescentes", iva="general", pvp="12.90",
         flags=("control_stock",)),
    # --- Iluminación / Pantallas ------------------------------------------
    dict(nombre="Pantalla Juwel MultiLux 100 cm", corto="Pantalla 100",
         familia="Iluminación/Pantallas", iva="general", pvp="129.00",
         flags=("control_stock",)),
    # --- Calentadores ------------------------------------------------------
    dict(nombre="Calentador sumergible 100 W", corto="Calent. 100W",
         familia="Calentadores", iva="general", pvp="16.90",
         flags=("control_stock",)),
    dict(nombre="Calentador sumergible 200 W", corto="Calent. 200W",
         familia="Calentadores", iva="general", pvp="21.90",
         flags=("control_stock",)),
    # --- Aireadores --------------------------------------------------------
    dict(nombre="Bomba de aire 2 salidas", corto="Bomba aire",
         familia="Aireadores", iva="general", pvp="14.50",
         flags=("control_stock",)),
    # --- Comederos ---------------------------------------------------------
    dict(nombre="Comedero automático digital", corto="Comedero auto",
         familia="Comederos", iva="general", pvp="22.90",
         flags=("control_stock",)),
    # --- Decoración / Gravas y sustratos ----------------------------------
    dict(nombre="JBL Arena Sansibar white 5 kg", corto="Arena white",
         familia="Decoración/Gravas y sustratos", iva="general", pvp="16.90",
         flags=("control_stock",), ean="4014162670557"),
    dict(nombre="Sustrato nutritivo plantado 3 L", corto="Sustrato 3L",
         familia="Decoración/Gravas y sustratos", iva="general", pvp="18.50",
         flags=("control_stock",)),
    # --- Decoración / Maderas (a granel: precio libre) --------------------
    dict(nombre="Madera natural al peso", corto="Madera peso",
         familia="Decoración/Maderas", iva="general", pvp="12.00",
         flags=("precio_libre",)),
    # --- Decoración / Rocas ------------------------------------------------
    dict(nombre="Roca Seiryu al peso", corto="Roca Seiryu",
         familia="Decoración/Rocas", iva="general", pvp="4.50",
         flags=("precio_libre",)),
    # --- Decoración / Artificiales ----------------------------------------
    dict(nombre="Coco Java tamaño M (decoración)", corto="Coco Java M",
         familia="Decoración/Artificiales", iva="general", pvp="6.90",
         flags=("control_stock",)),
    # --- Decoración / Fondos ----------------------------------------------
    dict(nombre="Fondo decorativo doble cara 60 cm (por metro)", corto="Fondo 60",
         familia="Decoración/Fondos", iva="general", pvp="8.90",
         flags=("precio_libre",)),
    # --- Acuarios / Kits ---------------------------------------------------
    dict(nombre="Kit acuario 100 L con equipamiento", corto="Kit 100L",
         familia="Acuarios/Kits", iva="general", pvp="169.00",
         flags=("control_stock",)),
    dict(nombre="Acuario Vivaline 126 L", corto="Vivaline 126",
         familia="Acuarios/Kits", iva="general", pvp="299.00",
         flags=("control_stock",)),
    # --- Acuarios / Urnas de cristal --------------------------------------
    dict(nombre="Urna de cristal 60x30x30", corto="Urna 60",
         familia="Acuarios/Urnas de cristal", iva="general", pvp="45.00",
         flags=("control_stock",)),
    # --- Accesorios --------------------------------------------------------
    # Bolsa de transporte: importe simbolico, boton fijo de cobro rapido en el inicio.
    dict(nombre="Bolsa de transporte para peces", corto="Bolsa",
         familia="Accesorios", iva="general", pvp="0.10"),
    dict(nombre="Red para peces 10 cm", corto="Red 10cm",
         familia="Accesorios", iva="general", pvp="2.50",
         flags=("control_stock",)),
    dict(nombre="Imán limpiacristales mediano", corto="Imán limpia",
         familia="Accesorios", iva="general", pvp="9.90",
         flags=("control_stock",)),
    dict(nombre="Termómetro digital adhesivo", corto="Termómetro",
         familia="Accesorios", iva="general", pvp="4.50",
         flags=("control_stock",)),
    dict(nombre="Tubo silicona aireación (por metro)", corto="Silicona m",
         familia="Accesorios", iva="general", pvp="0.80",
         flags=("precio_libre",)),
]

# Clientes de demostracion. Variedad deliberada para ejercitar los casos
# fiscales del TPV:
#   - sin NIF -> factura simplificada normal (art. 7 ROF)
#   - con NIF + domicilio -> simplificada "cualificada" (art. 7.2 ROF) o
#     factura completa (F1) cuando la venta supere 3.000 EUR o el cliente sea
#     una empresa.
# NIF/CIF y contactos son ficticios (datos de demostracion, no reales).
CLIENTES: list[dict] = [
    # Sin NIF: venta al contado, simplificada normal.
    dict(nombre="Cliente al contado", rgpd=False),
    # Particulares con NIF + domicilio completos (cualificable).
    dict(nombre="María López García", nif="12345678Z",
         domicilio="Gran Vía 20, 3ºB, Madrid",
         email="maria.lopez@example.com", telefono="600123456", rgpd=True),
    dict(nombre="Jon Etxeberria Aguirre", nif="47852369H",
         domicilio="Av. de los Fueros 5, Vitoria-Gasteiz",
         telefono="945112233", rgpd=True),
    # Con NIF pero sin domicilio: datos parciales.
    dict(nombre="Ainhoa Zubizarreta", nif="39284756C",
         email="ainhoa.z@example.com", rgpd=True),
    # Empresa (CIF): destino tipico de factura completa F1.
    dict(nombre="Acuarios del Norte S.L.", nif="B95123456",
         domicilio="Polígono Ansio, Nave 12, Barakaldo",
         email="pedidos@acuariosnorte.example", telefono="944001122", rgpd=True),
    # Cliente historico de la demo (se conserva).
    dict(nombre="Cliente de prueba (demo)", nif="00000000T",
         domicilio="Calle Demo 1, Bilbao", rgpd=True),
]
